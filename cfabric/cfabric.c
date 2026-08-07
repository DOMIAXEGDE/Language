/*
 * cfabric.c - deterministic, collision-free graphical-world generator.
 *
 * Build:
 *   cc -std=c11 -Wall -Wextra -pedantic -O2 cfabric.c -o cfabric.exe
 *
 * Example:
 *   ./cfabric.exe --seed 42 --canvas-count 6 \
 *       --canvas-partition-count 12 --output world.json
 *
 * The CLI/config/UI pattern is adapted from 3.c.  Geometry follows the
 * supplied cfabric specification: an object is a point or a straight line;
 * a canvas is a closed shape with at least three points and three lines; a
 * canvas partition is exactly two points and one line.  Coordinates are
 * signed integers, hence exact rational valid-structure values.
 */

#include <ctype.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CF_VERSION "1.0.0"
#define CF_TEXT 256
#define CF_LINE_BUFFER 2048
#define CF_MAX_CANVASES 256U
#define CF_MAX_PARTITIONS 4096U
#define CF_MAX_DIMENSION 1000000LL
#define CF_MIN_CANVAS_SPAN 12LL
#define CF_ROLE_CANVAS 1U
#define CF_ROLE_PARTITION 2U

typedef struct { uint64_t state; } cf_rng;

typedef struct {
    uint64_t seed;
    int64_t width;
    int64_t height;
    uint32_t canvas_count;
    uint32_t partition_count;
    int64_t margin;
    int64_t gap;
    char output[CF_TEXT];
    char world_name[CF_TEXT];
} cf_config;

typedef struct {
    char id[32];
    int64_t x;
    int64_t y;
    uint32_t roles;
    size_t canvas_index;
    int64_t partition_index;
} cf_point;

typedef enum {
    CF_LINE_BOUNDARY = 0,
    CF_LINE_PARTITION = 1
} cf_line_kind;

typedef struct {
    char id[32];
    size_t a;
    size_t b;
    cf_line_kind kind;
    size_t canvas_index;
    int64_t partition_index;
} cf_line_object;

typedef struct {
    char id[32];
    size_t *points;
    size_t point_count;
    size_t *lines;
    size_t line_count;
    int64_t min_x;
    int64_t min_y;
    int64_t max_x;
    int64_t max_y;
    char fill[16];
    char stroke[16];
} cf_canvas;

typedef struct {
    char id[32];
    size_t canvas_index;
    size_t p1;
    size_t p2;
    size_t line_index;
} cf_partition;

typedef struct {
    cf_point *points;
    size_t point_count;
    size_t point_capacity;
    cf_line_object *lines;
    size_t line_count;
    size_t line_capacity;
    cf_canvas *canvases;
    size_t canvas_count;
    size_t canvas_capacity;
    cf_partition *partitions;
    size_t partition_count;
    size_t partition_capacity;
} cf_world;

typedef enum {
    CF_INTERSECTION_NONE = 0,
    CF_INTERSECTION_POINT = 1,
    CF_INTERSECTION_OVERLAP = 2
} cf_intersection_kind;

typedef struct {
    cf_intersection_kind kind;
    int64_t x;
    int64_t y;
} cf_intersection;

static const char *CF_FILLS[] = {
    "#dfe8ff", "#ffe4d6", "#e2f4df", "#f4e1ff",
    "#fff2bf", "#dff4f3", "#f7dfea", "#e8e8e8"
};
static const char *CF_STROKES[] = {
    "#274060", "#7a3e2f", "#315f3c", "#69417e",
    "#7c6217", "#236b68", "#7b3656", "#4b4b4b"
};

static bool cf_copy(char *dst, size_t capacity, const char *src) {
    size_t n;
    if (dst == NULL || src == NULL || capacity == 0U) return false;
    n = strlen(src);
    if (n >= capacity) return false;
    memcpy(dst, src, n + 1U);
    return true;
}

static int cf_lower(int value) { return tolower((unsigned char)value); }

static bool cf_ieq(const char *a, const char *b) {
    if (a == NULL || b == NULL) return false;
    while (*a != '\0' && *b != '\0') {
        if (cf_lower(*a) != cf_lower(*b)) return false;
        ++a; ++b;
    }
    return *a == '\0' && *b == '\0';
}

static char *cf_trim(char *text) {
    size_t n;
    char *comment;
    if (text == NULL) return NULL;
    while (*text != '\0' && isspace((unsigned char)*text)) ++text;
    comment = strchr(text, '#');
    if (comment != NULL) *comment = '\0';
    n = strlen(text);
    while (n > 0U && isspace((unsigned char)text[n - 1U])) {
        text[n - 1U] = '\0';
        --n;
    }
    return text;
}

static bool cf_split_setting(char *line, char **key, char **value) {
    char *separator;
    if (line == NULL || key == NULL || value == NULL) return false;
    separator = strchr(line, '=');
    if (separator != NULL) {
        *separator = '\0';
        *key = cf_trim(line);
        *value = cf_trim(separator + 1);
        return **key != '\0' && **value != '\0';
    }
    separator = line;
    while (*separator != '\0' && !isspace((unsigned char)*separator)) ++separator;
    if (*separator == '\0') return false;
    *separator = '\0';
    ++separator;
    *key = cf_trim(line);
    *value = cf_trim(separator);
    return **key != '\0' && **value != '\0';
}

static bool cf_parse_u64(const char *text, uint64_t *value) {
    char *end;
    unsigned long long parsed;
    if (text == NULL || value == NULL || *text == '\0' || *text == '-') return false;
    errno = 0;
    parsed = strtoull(text, &end, 0);
    if (errno != 0 || end == text || *cf_trim(end) != '\0') return false;
    *value = (uint64_t)parsed;
    return true;
}

static bool cf_parse_i64(const char *text, int64_t *value) {
    char *end;
    long long parsed;
    if (text == NULL || value == NULL || *text == '\0') return false;
    errno = 0;
    parsed = strtoll(text, &end, 0);
    if (errno != 0 || end == text || *cf_trim(end) != '\0') return false;
    *value = (int64_t)parsed;
    return true;
}

static bool cf_parse_u32(const char *text, uint32_t *value) {
    uint64_t parsed;
    if (!cf_parse_u64(text, &parsed) || parsed > UINT32_MAX) return false;
    *value = (uint32_t)parsed;
    return true;
}

static uint64_t cf_rng_next(cf_rng *rng) {
    uint64_t z;
    rng->state += UINT64_C(0x9e3779b97f4a7c15);
    z = rng->state;
    z = (z ^ (z >> 30U)) * UINT64_C(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27U)) * UINT64_C(0x94d049bb133111eb);
    return z ^ (z >> 31U);
}

static uint64_t cf_rng_bounded(cf_rng *rng, uint64_t bound) {
    uint64_t threshold;
    uint64_t value;
    if (bound <= 1U) return 0U;
    threshold = (uint64_t)(-bound) % bound;
    do { value = cf_rng_next(rng); } while (value < threshold);
    return value % bound;
}

static int64_t cf_min_i64(int64_t a, int64_t b) { return a < b ? a : b; }
static int64_t cf_max_i64(int64_t a, int64_t b) { return a > b ? a : b; }

static void cf_config_defaults(cf_config *config) {
    memset(config, 0, sizeof(*config));
    config->seed = UINT64_C(1);
    config->width = 1200;
    config->height = 800;
    config->canvas_count = 6U;
    config->partition_count = 12U;
    config->margin = 36;
    config->gap = 18;
    (void)cf_copy(config->output, sizeof(config->output), "world.json");
    (void)cf_copy(config->world_name, sizeof(config->world_name), "cfabric-world");
}

static bool cf_apply_setting(cf_config *config, const char *key, const char *value) {
    uint64_t seed;
    uint32_t count;
    int64_t number;
    if (config == NULL || key == NULL || value == NULL) return false;

    if (cf_ieq(key, "seed") || cf_ieq(key, "generation_seed")) {
        if (!cf_parse_u64(value, &seed)) return false;
        config->seed = seed;
        return true;
    }
    if (cf_ieq(key, "width") || cf_ieq(key, "canvas_width")) {
        if (!cf_parse_i64(value, &number)) return false;
        config->width = number;
        return true;
    }
    if (cf_ieq(key, "height") || cf_ieq(key, "canvas_height")) {
        if (!cf_parse_i64(value, &number)) return false;
        config->height = number;
        return true;
    }
    if (cf_ieq(key, "canvas_count") || cf_ieq(key, "canvases")) {
        if (!cf_parse_u32(value, &count)) return false;
        config->canvas_count = count;
        return true;
    }
    if (cf_ieq(key, "canvas_partition_count") ||
        cf_ieq(key, "partition_count") || cf_ieq(key, "partitions")) {
        if (!cf_parse_u32(value, &count)) return false;
        config->partition_count = count;
        return true;
    }
    if (cf_ieq(key, "margin")) {
        if (!cf_parse_i64(value, &number)) return false;
        config->margin = number;
        return true;
    }
    if (cf_ieq(key, "gap") || cf_ieq(key, "canvas_gap")) {
        if (!cf_parse_i64(value, &number)) return false;
        config->gap = number;
        return true;
    }
    if (cf_ieq(key, "output") || cf_ieq(key, "output_target") || cf_ieq(key, "file")) {
        return cf_copy(config->output, sizeof(config->output), value);
    }
    if (cf_ieq(key, "world_name") || cf_ieq(key, "name")) {
        return cf_copy(config->world_name, sizeof(config->world_name), value);
    }
    return false;
}

static bool cf_load_config(const char *path, cf_config *config) {
    FILE *stream;
    char buffer[CF_LINE_BUFFER];
    unsigned long long line_number = 0ULL;
    if (path == NULL || config == NULL) return false;
    stream = fopen(path, "r");
    if (stream == NULL) return false;

    while (fgets(buffer, sizeof(buffer), stream) != NULL) {
        char *line;
        char *key = NULL;
        char *value = NULL;
        ++line_number;
        line = cf_trim(buffer);
        if (*line == '\0' || cf_ieq(line, "end")) continue;
        if (!cf_split_setting(line, &key, &value) || !cf_apply_setting(config, key, value)) {
            fprintf(stderr, "Invalid configuration on line %llu: %s\n",
                    line_number, key != NULL ? key : line);
            fclose(stream);
            return false;
        }
    }
    fclose(stream);
    return true;
}

static bool cf_write_sample_config(const char *path) {
    FILE *stream = fopen(path, "w");
    if (stream == NULL) return false;
    fprintf(stream,
            "# cfabric deterministic world configuration\n"
            "world_name=example-world\n"
            "seed=42\n"
            "width=1200\n"
            "height=800\n"
            "canvas_count=6\n"
            "canvas_partition_count=12\n"
            "margin=36\n"
            "gap=18\n"
            "output_target=world.json\n"
            "end\n");
    fclose(stream);
    return true;
}

static bool cf_prompt_text(const char *label, char *target, size_t capacity) {
    char buffer[CF_LINE_BUFFER];
    size_t n;
    printf("%s [%s]: ", label, target);
    fflush(stdout);
    if (fgets(buffer, sizeof(buffer), stdin) == NULL) return false;
    n = strlen(buffer);
    if (n > 0U && buffer[n - 1U] == '\n') buffer[n - 1U] = '\0';
    return buffer[0] == '\0' || cf_copy(target, capacity, buffer);
}

static bool cf_prompt_number(const char *label, const char *key,
                             cf_config *config, long long current) {
    char buffer[CF_LINE_BUFFER];
    size_t n;
    printf("%s [%lld]: ", label, current);
    fflush(stdout);
    if (fgets(buffer, sizeof(buffer), stdin) == NULL) return false;
    n = strlen(buffer);
    if (n > 0U && buffer[n - 1U] == '\n') buffer[n - 1U] = '\0';
    return buffer[0] == '\0' || cf_apply_setting(config, key, buffer);
}

static bool cf_run_ui(cf_config *config) {
    return cf_prompt_text("world_name", config->world_name, sizeof(config->world_name)) &&
           cf_prompt_number("generation_seed", "seed", config,
                            (long long)config->seed) &&
           cf_prompt_number("width", "width", config, (long long)config->width) &&
           cf_prompt_number("height", "height", config, (long long)config->height) &&
           cf_prompt_number("canvas_count", "canvas_count", config,
                            (long long)config->canvas_count) &&
           cf_prompt_number("canvas_partition_count", "canvas_partition_count", config,
                            (long long)config->partition_count) &&
           cf_prompt_number("margin", "margin", config, (long long)config->margin) &&
           cf_prompt_number("gap", "gap", config, (long long)config->gap) &&
           cf_prompt_text("output_target", config->output, sizeof(config->output));
}

static void cf_usage(const char *program) {
    fprintf(stderr,
            "Usage:\n"
            "  %s --ui\n"
            "  %s --config <path> [overrides]\n"
            "  %s --sample-config <path>\n"
            "  %s [world flags]\n"
            "\n"
            "World flags:\n"
            "  --seed, -s <u64>                       deterministic seed\n"
            "  --width, -W <n>                        world width\n"
            "  --height, -H <n>                       world height\n"
            "  --canvas-count, -c <n>                 closed canvas count\n"
            "  --canvas-partition-count, -p <n>       total partition count\n"
            "  --margin <n>                           outer margin\n"
            "  --gap <n>                              minimum grid-cell separation\n"
            "  --world-name, -n <text>                world name\n"
            "  --output, --output-target, -o <path>   JSON path, stdout, or -\n"
            "  --config <path>                        key=value configuration\n"
            "  --sample-config <path>                 write example configuration\n"
            "  --ui                                   interactive micro UI\n",
            program, program, program, program);
}

static bool cf_validate_config(const cf_config *config) {
    uint32_t cols = 1U;
    uint32_t rows;
    uint32_t max_per_canvas;
    int64_t usable_width;
    int64_t usable_height;
    int64_t required_span;

    if (config->canvas_count == 0U || config->canvas_count > CF_MAX_CANVASES) {
        fprintf(stderr, "canvas_count must be in [1, %u]\n", CF_MAX_CANVASES);
        return false;
    }
    if (config->partition_count > CF_MAX_PARTITIONS) {
        fprintf(stderr, "canvas_partition_count must not exceed %u\n", CF_MAX_PARTITIONS);
        return false;
    }
    if (config->width <= 0 || config->height <= 0 ||
        config->width > CF_MAX_DIMENSION || config->height > CF_MAX_DIMENSION) {
        fprintf(stderr, "width and height must be in [1, %lld]\n",
                (long long)CF_MAX_DIMENSION);
        return false;
    }
    if (config->margin < 0 || config->gap < 1) {
        fprintf(stderr, "margin must be non-negative and gap must be at least 1\n");
        return false;
    }
    if (config->output[0] == '\0' || config->world_name[0] == '\0') {
        fprintf(stderr, "world_name and output_target cannot be empty\n");
        return false;
    }

    while ((uint64_t)cols * (uint64_t)cols < config->canvas_count) ++cols;
    rows = (config->canvas_count + cols - 1U) / cols;
    usable_width = config->width - 2 * config->margin;
    usable_height = config->height - 2 * config->margin;
    if (usable_width <= 0 || usable_height <= 0) {
        fprintf(stderr, "margin leaves no usable area\n");
        return false;
    }

    max_per_canvas = (config->partition_count + config->canvas_count - 1U) /
                     config->canvas_count;
    required_span = cf_max_i64(CF_MIN_CANVAS_SPAN,
                               (int64_t)max_per_canvas + 2);
    if (usable_width / (int64_t)cols - 2 * config->gap < required_span ||
        usable_height / (int64_t)rows - 2 * config->gap < CF_MIN_CANVAS_SPAN) {
        fprintf(stderr,
                "world is too small for the requested structures; increase dimensions "
                "or reduce counts/margin/gap\n");
        return false;
    }
    return true;
}

static int cf_parse_arguments(int argc, char **argv, cf_config *config,
                              bool *should_run) {
    int i;
    const char *config_path = NULL;
    bool use_ui = false;

    *should_run = false;
    cf_config_defaults(config);
    if (argc <= 1) {
        cf_usage(argv[0]);
        return 0;
    }

    for (i = 1; i < argc; ++i) {
        if (cf_ieq(argv[i], "--help") || cf_ieq(argv[i], "-h")) {
            cf_usage(argv[0]);
            return 0;
        }
        if (cf_ieq(argv[i], "--sample-config")) {
            if (i + 1 >= argc) {
                cf_usage(argv[0]);
                return 1;
            }
            if (!cf_write_sample_config(argv[i + 1])) {
                perror("unable to write sample config");
                return 1;
            }
            return 0;
        }
        if (cf_ieq(argv[i], "--config")) {
            if (i + 1 >= argc) {
                cf_usage(argv[0]);
                return 1;
            }
            config_path = argv[++i];
        } else if (cf_ieq(argv[i], "--ui")) {
            use_ui = true;
        }
    }

    if (config_path != NULL && !cf_load_config(config_path, config)) {
        perror("unable to load config");
        return 1;
    }

    for (i = 1; i < argc; ++i) {
        const char *flag = argv[i];
        const char *key = NULL;
        const char *value;

        if (cf_ieq(flag, "--config") || cf_ieq(flag, "--sample-config")) {
            ++i;
            continue;
        }
        if (cf_ieq(flag, "--ui") || cf_ieq(flag, "--help") || cf_ieq(flag, "-h")) {
            continue;
        }
        if (i + 1 >= argc) {
            fprintf(stderr, "missing value for %s\n", flag);
            return 1;
        }
        value = argv[++i];

        if (cf_ieq(flag, "--seed") || cf_ieq(flag, "-s")) key = "seed";
        else if (cf_ieq(flag, "--width") || cf_ieq(flag, "-W")) key = "width";
        else if (cf_ieq(flag, "--height") || cf_ieq(flag, "-H")) key = "height";
        else if (cf_ieq(flag, "--canvas-count") || cf_ieq(flag, "-c")) key = "canvas_count";
        else if (cf_ieq(flag, "--canvas-partition-count") ||
                 cf_ieq(flag, "--partition-count") || cf_ieq(flag, "-p"))
            key = "canvas_partition_count";
        else if (cf_ieq(flag, "--margin")) key = "margin";
        else if (cf_ieq(flag, "--gap")) key = "gap";
        else if (cf_ieq(flag, "--world-name") || cf_ieq(flag, "-n")) key = "world_name";
        else if (cf_ieq(flag, "--output") || cf_ieq(flag, "--output-target") ||
                 cf_ieq(flag, "-o")) key = "output_target";
        else {
            fprintf(stderr, "unknown flag: %s\n", flag);
            cf_usage(argv[0]);
            return 1;
        }

        if (!cf_apply_setting(config, key, value)) {
            fprintf(stderr, "invalid value for %s: %s\n", flag, value);
            return 1;
        }
    }

    if (use_ui && !cf_run_ui(config)) {
        fprintf(stderr, "invalid UI input\n");
        return 1;
    }
    if (!cf_validate_config(config)) return 1;
    *should_run = true;
    return 0;
}

static bool cf_world_init(cf_world *world, uint32_t canvas_count,
                          uint32_t partition_count) {
    size_t point_capacity = (size_t)4U * canvas_count +
                            (size_t)2U * partition_count;
    size_t line_capacity = (size_t)4U * canvas_count +
                           (size_t)3U * partition_count;
    memset(world, 0, sizeof(*world));
    world->point_capacity = point_capacity;
    world->line_capacity = line_capacity;
    world->canvas_capacity = canvas_count;
    world->partition_capacity = partition_count;
    world->points = (cf_point *)calloc(point_capacity, sizeof(*world->points));
    world->lines = (cf_line_object *)calloc(line_capacity, sizeof(*world->lines));
    world->canvases = (cf_canvas *)calloc(canvas_count, sizeof(*world->canvases));
    if (partition_count > 0U)
        world->partitions = (cf_partition *)calloc(partition_count,
                                                    sizeof(*world->partitions));
    return world->points != NULL && world->lines != NULL && world->canvases != NULL &&
           (partition_count == 0U || world->partitions != NULL);
}

static void cf_world_free(cf_world *world) {
    size_t i;
    if (world == NULL) return;
    for (i = 0U; i < world->canvas_count; ++i) {
        free(world->canvases[i].points);
        free(world->canvases[i].lines);
    }
    free(world->points);
    free(world->lines);
    free(world->canvases);
    free(world->partitions);
    memset(world, 0, sizeof(*world));
}

static bool cf_add_point(cf_world *world, int64_t x, int64_t y, uint32_t roles,
                         size_t canvas_index, int64_t partition_index,
                         size_t *point_index) {
    cf_point *point;
    if (world->point_count >= world->point_capacity) return false;
    *point_index = world->point_count;
    point = &world->points[world->point_count++];
    (void)snprintf(point->id, sizeof(point->id), "xP%06zu", *point_index + 1U);
    point->x = x;
    point->y = y;
    point->roles = roles;
    point->canvas_index = canvas_index;
    point->partition_index = partition_index;
    return true;
}

static bool cf_add_line(cf_world *world, size_t a, size_t b, cf_line_kind kind,
                        size_t canvas_index, int64_t partition_index,
                        size_t *line_index) {
    cf_line_object *line;
    if (world->line_count >= world->line_capacity) return false;
    *line_index = world->line_count;
    line = &world->lines[world->line_count++];
    (void)snprintf(line->id, sizeof(line->id), "xL%06zu", *line_index + 1U);
    line->a = a;
    line->b = b;
    line->kind = kind;
    line->canvas_index = canvas_index;
    line->partition_index = partition_index;
    return true;
}

static bool cf_add_partition(cf_world *world, size_t canvas_index,
                             size_t p1, size_t p2, size_t line_index,
                             size_t *partition_index) {
    cf_partition *partition;
    if (world->partition_count >= world->partition_capacity) return false;
    *partition_index = world->partition_count;
    partition = &world->partitions[world->partition_count++];
    (void)snprintf(partition->id, sizeof(partition->id), "xZ%06zu",
                   *partition_index + 1U);
    partition->canvas_index = canvas_index;
    partition->p1 = p1;
    partition->p2 = p2;
    partition->line_index = line_index;
    return true;
}

static bool cf_build_canvas(cf_world *world, cf_rng *rng,
                            int64_t min_x, int64_t min_y,
                            int64_t max_x, int64_t max_y,
                            uint32_t partition_count, bool vertical) {
    size_t canvas_index;
    cf_canvas *canvas;
    size_t boundary_count = 4U + (size_t)2U * partition_count;
    int64_t *positions = NULL;
    size_t *first_side = NULL;
    size_t *second_side = NULL;
    size_t global_partition_start;
    size_t palette_index;
    size_t cursor = 0U;
    size_t i;

    if (world->canvas_count >= world->canvas_capacity ||
        min_x >= max_x || min_y >= max_y) return false;

    canvas_index = world->canvas_count;
    canvas = &world->canvases[world->canvas_count++];
    (void)snprintf(canvas->id, sizeof(canvas->id), "xC%04zu", canvas_index + 1U);
    canvas->point_count = boundary_count;
    canvas->line_count = boundary_count;
    canvas->points = (size_t *)calloc(boundary_count, sizeof(*canvas->points));
    canvas->lines = (size_t *)calloc(boundary_count, sizeof(*canvas->lines));
    if (canvas->points == NULL || canvas->lines == NULL) return false;

    canvas->min_x = min_x;
    canvas->min_y = min_y;
    canvas->max_x = max_x;
    canvas->max_y = max_y;
    palette_index = (size_t)cf_rng_bounded(
        rng, sizeof(CF_FILLS) / sizeof(CF_FILLS[0]));
    (void)cf_copy(canvas->fill, sizeof(canvas->fill), CF_FILLS[palette_index]);
    (void)cf_copy(canvas->stroke, sizeof(canvas->stroke), CF_STROKES[palette_index]);

    if (partition_count > 0U) {
        positions = (int64_t *)calloc(partition_count, sizeof(*positions));
        first_side = (size_t *)calloc(partition_count, sizeof(*first_side));
        second_side = (size_t *)calloc(partition_count, sizeof(*second_side));
        if (positions == NULL || first_side == NULL || second_side == NULL) goto fail;

        for (i = 0U; i < partition_count; ++i) {
            int64_t span = vertical ? max_x - min_x : max_y - min_y;
            positions[i] = (vertical ? min_x : min_y) +
                           ((int64_t)(i + 1U) * span) /
                           (int64_t)(partition_count + 1U);
            if ((i > 0U && positions[i] <= positions[i - 1U]) ||
                positions[i] <= (vertical ? min_x : min_y) ||
                positions[i] >= (vertical ? max_x : max_y)) goto fail;
        }
    }

    global_partition_start = world->partition_count;

    if (vertical) {
        size_t point_index;
        if (!cf_add_point(world, min_x, min_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;

        for (i = 0U; i < partition_count; ++i) {
            if (!cf_add_point(world, positions[i], min_y,
                              CF_ROLE_CANVAS | CF_ROLE_PARTITION,
                              canvas_index,
                              (int64_t)(global_partition_start + i),
                              &point_index)) goto fail;
            first_side[i] = point_index;
            canvas->points[cursor++] = point_index;
        }

        if (!cf_add_point(world, max_x, min_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;
        if (!cf_add_point(world, max_x, max_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;

        for (i = partition_count; i > 0U; --i) {
            size_t p = i - 1U;
            if (!cf_add_point(world, positions[p], max_y,
                              CF_ROLE_CANVAS | CF_ROLE_PARTITION,
                              canvas_index,
                              (int64_t)(global_partition_start + p),
                              &point_index)) goto fail;
            second_side[p] = point_index;
            canvas->points[cursor++] = point_index;
        }

        if (!cf_add_point(world, min_x, max_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;
    } else {
        size_t point_index;
        if (!cf_add_point(world, min_x, min_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;
        if (!cf_add_point(world, max_x, min_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;

        for (i = 0U; i < partition_count; ++i) {
            if (!cf_add_point(world, max_x, positions[i],
                              CF_ROLE_CANVAS | CF_ROLE_PARTITION,
                              canvas_index,
                              (int64_t)(global_partition_start + i),
                              &point_index)) goto fail;
            first_side[i] = point_index;
            canvas->points[cursor++] = point_index;
        }

        if (!cf_add_point(world, max_x, max_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;
        if (!cf_add_point(world, min_x, max_y, CF_ROLE_CANVAS,
                          canvas_index, -1, &point_index)) goto fail;
        canvas->points[cursor++] = point_index;

        for (i = partition_count; i > 0U; --i) {
            size_t p = i - 1U;
            if (!cf_add_point(world, min_x, positions[p],
                              CF_ROLE_CANVAS | CF_ROLE_PARTITION,
                              canvas_index,
                              (int64_t)(global_partition_start + p),
                              &point_index)) goto fail;
            second_side[p] = point_index;
            canvas->points[cursor++] = point_index;
        }
    }

    if (cursor != boundary_count) goto fail;

    for (i = 0U; i < boundary_count; ++i) {
        size_t line_index;
        if (!cf_add_line(world, canvas->points[i],
                         canvas->points[(i + 1U) % boundary_count],
                         CF_LINE_BOUNDARY, canvas_index, -1, &line_index)) goto fail;
        canvas->lines[i] = line_index;
    }

    for (i = 0U; i < partition_count; ++i) {
        size_t line_index;
        size_t partition_index;
        if (!cf_add_line(world, first_side[i], second_side[i],
                         CF_LINE_PARTITION, canvas_index,
                         (int64_t)(global_partition_start + i),
                         &line_index)) goto fail;
        if (!cf_add_partition(world, canvas_index, first_side[i], second_side[i],
                              line_index, &partition_index)) goto fail;
        if (partition_index != global_partition_start + i) goto fail;
    }

    free(positions);
    free(first_side);
    free(second_side);
    return true;

fail:
    free(positions);
    free(first_side);
    free(second_side);
    return false;
}

static bool cf_generate_world(const cf_config *config, cf_world *world) {
    cf_rng rng;
    uint32_t cols = 1U;
    uint32_t rows;
    uint32_t *distribution = NULL;
    uint32_t *order = NULL;
    uint32_t base;
    uint32_t remainder;
    uint32_t i;
    int64_t usable_width;
    int64_t usable_height;

    rng.state = config->seed;
    if (!cf_world_init(world, config->canvas_count, config->partition_count))
        return false;

    distribution = (uint32_t *)calloc(config->canvas_count, sizeof(*distribution));
    order = (uint32_t *)calloc(config->canvas_count, sizeof(*order));
    if (distribution == NULL || order == NULL) goto fail;

    base = config->partition_count / config->canvas_count;
    remainder = config->partition_count % config->canvas_count;
    for (i = 0U; i < config->canvas_count; ++i) {
        distribution[i] = base;
        order[i] = i;
    }
    for (i = config->canvas_count; i > 1U; --i) {
        uint32_t j = (uint32_t)cf_rng_bounded(&rng, i);
        uint32_t tmp = order[i - 1U];
        order[i - 1U] = order[j];
        order[j] = tmp;
    }
    for (i = 0U; i < remainder; ++i) ++distribution[order[i]];

    while ((uint64_t)cols * (uint64_t)cols < config->canvas_count) ++cols;
    rows = (config->canvas_count + cols - 1U) / cols;
    usable_width = config->width - 2 * config->margin;
    usable_height = config->height - 2 * config->margin;

    for (i = 0U; i < config->canvas_count; ++i) {
        uint32_t row = i / cols;
        uint32_t col = i % cols;
        int64_t cell_x0 = config->margin +
                          usable_width * (int64_t)col / (int64_t)cols;
        int64_t cell_x1 = config->margin +
                          usable_width * (int64_t)(col + 1U) / (int64_t)cols;
        int64_t cell_y0 = config->margin +
                          usable_height * (int64_t)row / (int64_t)rows;
        int64_t cell_y1 = config->margin +
                          usable_height * (int64_t)(row + 1U) / (int64_t)rows;
        int64_t inner_x0 = cell_x0 + config->gap;
        int64_t inner_x1 = cell_x1 - config->gap;
        int64_t inner_y0 = cell_y0 + config->gap;
        int64_t inner_y1 = cell_y1 - config->gap;
        int64_t required_x = cf_max_i64(CF_MIN_CANVAS_SPAN,
                                        (int64_t)distribution[i] + 2);
        int64_t extra_x = (inner_x1 - inner_x0) - required_x;
        int64_t extra_y = (inner_y1 - inner_y0) - CF_MIN_CANVAS_SPAN;
        int64_t inset_x_total;
        int64_t inset_y_total;
        int64_t inset_left;
        int64_t inset_top;
        int64_t min_x;
        int64_t min_y;
        int64_t max_x;
        int64_t max_y;
        bool can_vertical;
        bool can_horizontal;
        bool vertical;

        if (extra_x < 0 || extra_y < 0) goto fail;
        inset_x_total = (int64_t)cf_rng_bounded(
            &rng, (uint64_t)(extra_x / 2 + 1));
        inset_y_total = (int64_t)cf_rng_bounded(
            &rng, (uint64_t)(extra_y / 2 + 1));
        inset_left = (int64_t)cf_rng_bounded(
            &rng, (uint64_t)(inset_x_total + 1));
        inset_top = (int64_t)cf_rng_bounded(
            &rng, (uint64_t)(inset_y_total + 1));

        min_x = inner_x0 + inset_left;
        max_x = inner_x1 - (inset_x_total - inset_left);
        min_y = inner_y0 + inset_top;
        max_y = inner_y1 - (inset_y_total - inset_top);

        can_vertical = max_x - min_x - 1 >= (int64_t)distribution[i];
        can_horizontal = max_y - min_y - 1 >= (int64_t)distribution[i];
        if (!can_vertical && !can_horizontal) goto fail;
        vertical = can_vertical &&
                   (!can_horizontal || cf_rng_bounded(&rng, 2U) == 0U);

        if (!cf_build_canvas(world, &rng, min_x, min_y, max_x, max_y,
                             distribution[i], vertical)) goto fail;
    }

    free(distribution);
    free(order);
    return true;

fail:
    free(distribution);
    free(order);
    return false;
}

static bool cf_between(int64_t value, int64_t a, int64_t b) {
    return value >= cf_min_i64(a, b) && value <= cf_max_i64(a, b);
}

static bool cf_point_on_line(const cf_point *point,
                             const cf_point *a, const cf_point *b) {
    if (a->y == b->y)
        return point->y == a->y && cf_between(point->x, a->x, b->x);
    if (a->x == b->x)
        return point->x == a->x && cf_between(point->y, a->y, b->y);
    return false;
}

static cf_intersection cf_line_intersection(const cf_point *a1,
                                            const cf_point *a2,
                                            const cf_point *b1,
                                            const cf_point *b2) {
    cf_intersection result = {CF_INTERSECTION_NONE, 0, 0};
    bool a_horizontal = a1->y == a2->y;
    bool b_horizontal = b1->y == b2->y;

    if (a_horizontal && b_horizontal) {
        int64_t low;
        int64_t high;
        if (a1->y != b1->y) return result;
        low = cf_max_i64(cf_min_i64(a1->x, a2->x),
                         cf_min_i64(b1->x, b2->x));
        high = cf_min_i64(cf_max_i64(a1->x, a2->x),
                          cf_max_i64(b1->x, b2->x));
        if (low > high) return result;
        result.kind = low < high ? CF_INTERSECTION_OVERLAP : CF_INTERSECTION_POINT;
        result.x = low;
        result.y = a1->y;
        return result;
    }

    if (!a_horizontal && !b_horizontal) {
        int64_t low;
        int64_t high;
        if (a1->x != b1->x) return result;
        low = cf_max_i64(cf_min_i64(a1->y, a2->y),
                         cf_min_i64(b1->y, b2->y));
        high = cf_min_i64(cf_max_i64(a1->y, a2->y),
                          cf_max_i64(b1->y, b2->y));
        if (low > high) return result;
        result.kind = low < high ? CF_INTERSECTION_OVERLAP : CF_INTERSECTION_POINT;
        result.x = a1->x;
        result.y = low;
        return result;
    }

    if (a_horizontal) {
        if (cf_between(b1->x, a1->x, a2->x) &&
            cf_between(a1->y, b1->y, b2->y)) {
            result.kind = CF_INTERSECTION_POINT;
            result.x = b1->x;
            result.y = a1->y;
        }
    } else if (cf_between(a1->x, b1->x, b2->x) &&
               cf_between(b1->y, a1->y, a2->y)) {
        result.kind = CF_INTERSECTION_POINT;
        result.x = a1->x;
        result.y = b1->y;
    }
    return result;
}

static bool cf_is_endpoint_at(const cf_world *world,
                              const cf_line_object *line,
                              int64_t x, int64_t y) {
    const cf_point *a = &world->points[line->a];
    const cf_point *b = &world->points[line->b];
    return (a->x == x && a->y == y) || (b->x == x && b->y == y);
}

static bool cf_validate_world(const cf_config *config, const cf_world *world) {
    size_t i;
    size_t j;

    if (world->canvas_count != config->canvas_count ||
        world->partition_count != config->partition_count) {
        fprintf(stderr, "generated counts do not match requested counts\n");
        return false;
    }

    for (i = 0U; i < world->point_count; ++i) {
        const cf_point *p = &world->points[i];
        if (p->x < 0 || p->x > config->width ||
            p->y < 0 || p->y > config->height) {
            fprintf(stderr, "point %s lies outside world bounds\n", p->id);
            return false;
        }
        for (j = i + 1U; j < world->point_count; ++j) {
            const cf_point *q = &world->points[j];
            if (p->x == q->x && p->y == q->y) {
                fprintf(stderr, "point collision between %s and %s\n", p->id, q->id);
                return false;
            }
        }
    }

    for (i = 0U; i < world->canvas_count; ++i) {
        const cf_canvas *canvas = &world->canvases[i];
        if (canvas->point_count < 3U || canvas->line_count < 3U ||
            canvas->point_count + canvas->line_count < 6U ||
            canvas->point_count != canvas->line_count) {
            fprintf(stderr, "canvas %s is not a valid closed structure\n", canvas->id);
            return false;
        }
        for (j = 0U; j < canvas->line_count; ++j) {
            size_t line_index = canvas->lines[j];
            size_t expected_a = canvas->points[j];
            size_t expected_b = canvas->points[(j + 1U) % canvas->point_count];
            const cf_line_object *line;
            if (line_index >= world->line_count) return false;
            line = &world->lines[line_index];
            if (line->kind != CF_LINE_BOUNDARY || line->canvas_index != i ||
                !((line->a == expected_a && line->b == expected_b) ||
                  (line->a == expected_b && line->b == expected_a))) {
                fprintf(stderr, "canvas %s boundary is not closed in object order\n",
                        canvas->id);
                return false;
            }
        }
        for (j = i + 1U; j < world->canvas_count; ++j) {
            const cf_canvas *other = &world->canvases[j];
            bool separated = canvas->max_x < other->min_x ||
                             other->max_x < canvas->min_x ||
                             canvas->max_y < other->min_y ||
                             other->max_y < canvas->min_y;
            if (!separated) {
                fprintf(stderr, "canvas collision between %s and %s\n",
                        canvas->id, other->id);
                return false;
            }
        }
    }

    for (i = 0U; i < world->partition_count; ++i) {
        const cf_partition *partition = &world->partitions[i];
        const cf_line_object *line;
        if (partition->canvas_index >= world->canvas_count ||
            partition->p1 >= world->point_count ||
            partition->p2 >= world->point_count ||
            partition->line_index >= world->line_count) {
            fprintf(stderr, "partition %s has invalid references\n", partition->id);
            return false;
        }
        line = &world->lines[partition->line_index];
        if (line->kind != CF_LINE_PARTITION ||
            line->canvas_index != partition->canvas_index ||
            line->partition_index != (int64_t)i ||
            !((line->a == partition->p1 && line->b == partition->p2) ||
              (line->a == partition->p2 && line->b == partition->p1))) {
            fprintf(stderr, "partition %s is not two points plus one line\n",
                    partition->id);
            return false;
        }
    }

    for (i = 0U; i < world->line_count; ++i) {
        const cf_line_object *line = &world->lines[i];
        const cf_point *a;
        const cf_point *b;
        if (line->a >= world->point_count || line->b >= world->point_count ||
            line->a == line->b) {
            fprintf(stderr, "line %s has invalid endpoints\n", line->id);
            return false;
        }
        a = &world->points[line->a];
        b = &world->points[line->b];
        if (!((a->x == b->x) ^ (a->y == b->y))) {
            fprintf(stderr, "line %s is not a non-zero axis-aligned line\n", line->id);
            return false;
        }

        for (j = 0U; j < world->point_count; ++j) {
            if (j != line->a && j != line->b &&
                cf_point_on_line(&world->points[j], a, b)) {
                fprintf(stderr, "point-line collision between %s and %s\n",
                        world->points[j].id, line->id);
                return false;
            }
        }

        for (j = i + 1U; j < world->line_count; ++j) {
            const cf_line_object *other = &world->lines[j];
            const cf_point *c = &world->points[other->a];
            const cf_point *d = &world->points[other->b];
            cf_intersection intersection = cf_line_intersection(a, b, c, d);
            if (intersection.kind == CF_INTERSECTION_NONE) continue;
            if (intersection.kind == CF_INTERSECTION_OVERLAP) {
                fprintf(stderr, "line overlap between %s and %s\n",
                        line->id, other->id);
                return false;
            }
            if (!(line->canvas_index == other->canvas_index &&
                  cf_is_endpoint_at(world, line, intersection.x, intersection.y) &&
                  cf_is_endpoint_at(world, other, intersection.x, intersection.y))) {
                fprintf(stderr, "line collision between %s and %s at (%lld,%lld)\n",
                        line->id, other->id,
                        (long long)intersection.x, (long long)intersection.y);
                return false;
            }
        }
    }

    return true;
}

static void cf_json_string(FILE *stream, const char *text) {
    const unsigned char *cursor = (const unsigned char *)text;
    fputc('"', stream);
    while (*cursor != '\0') {
        unsigned char ch = *cursor++;
        switch (ch) {
            case '"': fputs("\\\"", stream); break;
            case '\\': fputs("\\\\", stream); break;
            case '\b': fputs("\\b", stream); break;
            case '\f': fputs("\\f", stream); break;
            case '\n': fputs("\\n", stream); break;
            case '\r': fputs("\\r", stream); break;
            case '\t': fputs("\\t", stream); break;
            default:
                if (ch < 0x20U) fprintf(stream, "\\u%04x", (unsigned int)ch);
                else fputc((int)ch, stream);
                break;
        }
    }
    fputc('"', stream);
}

static bool cf_write_json(FILE *stream, const cf_config *config,
                          const cf_world *world) {
    size_t i;
    size_t j;

    fputs("{\n", stream);
    fputs("  \"schema\": \"cfabric-world/1\",\n", stream);
    fputs("  \"generator\": {\"name\": \"cfabric\", \"version\": \""
          CF_VERSION "\", \"deterministic\": true},\n", stream);
    fputs("  \"world\": {\n    \"name\": ", stream);
    cf_json_string(stream, config->world_name);
    fprintf(stream,
            ",\n    \"seed\": \"%llu\",\n"
            "    \"dimensions\": 2,\n"
            "    \"bounds\": {\"min_x\": 0, \"min_y\": 0, "
            "\"max_x\": %lld, \"max_y\": %lld, "
            "\"width\": %lld, \"height\": %lld}\n"
            "  },\n",
            (unsigned long long)config->seed,
            (long long)config->width, (long long)config->height,
            (long long)config->width, (long long)config->height);

    fputs("  \"valid_structure\": {\n"
          "    \"object_types\": [\"point\", \"straight-line\"],\n"
          "    \"number_domain\": [\"zero\", \"negative-rational\", "
          "\"positive-rational\"],\n"
          "    \"coordinate_encoding\": \"signed-integer-rational\",\n"
          "    \"canvas_minimum\": {\"points\": 3, \"straight_lines\": 3, "
          "\"objects\": 6},\n"
          "    \"canvas_partition_exact\": {\"points\": 2, "
          "\"straight_lines\": 1, \"objects\": 3}\n"
          "  },\n", stream);

    fprintf(stream,
            "  \"counts\": {\"objects\": %zu, \"points\": %zu, "
            "\"straight_lines\": %zu, \"canvases\": %zu, "
            "\"canvas_partitions\": %zu},\n",
            world->point_count + world->line_count,
            world->point_count, world->line_count,
            world->canvas_count, world->partition_count);

    fprintf(stream,
            "  \"fabric_counts\": {\n"
            "    \"object_count\": {\"a\": %zu, \"b\": 1, \"x\": %zu},\n"
            "    \"canvas_count\": {\"c\": %zu, \"d\": 1, \"y\": %zu},\n"
            "    \"canvas_partition_count\": {\"e\": %zu, \"f\": 1, \"z\": %zu},\n"
            "    \"xor_signature\": %zu,\n"
            "    \"valid_structure_expression\": \"<x xor y xor z> * ((<x xor y xor z>) ^ <x xor y xor z>)\"\n"
            "  },\n",
            world->point_count + world->line_count,
            world->point_count + world->line_count,
            world->canvas_count, world->canvas_count,
            world->partition_count, world->partition_count,
            (world->point_count + world->line_count) ^
                world->canvas_count ^ world->partition_count);

    fputs("  \"objects\": {\n    \"points\": [\n", stream);
    for (i = 0U; i < world->point_count; ++i) {
        const cf_point *point = &world->points[i];
        const cf_canvas *canvas = &world->canvases[point->canvas_index];
        fprintf(stream,
                "      {\"id\": \"%s\", \"type\": \"point\", "
                "\"x\": %lld, \"y\": %lld, \"roles\": [\"canvas\"",
                point->id, (long long)point->x, (long long)point->y);
        if ((point->roles & CF_ROLE_PARTITION) != 0U)
            fputs(", \"canvas-partition\"", stream);
        fprintf(stream, "], \"canvas_id\": \"%s\"", canvas->id);
        if (point->partition_index >= 0) {
            fprintf(stream, ", \"partition_id\": \"%s\"",
                    world->partitions[(size_t)point->partition_index].id);
        }
        fprintf(stream, "}%s\n", i + 1U == world->point_count ? "" : ",");
    }

    fputs("    ],\n    \"straight_lines\": [\n", stream);
    for (i = 0U; i < world->line_count; ++i) {
        const cf_line_object *line = &world->lines[i];
        const cf_canvas *canvas = &world->canvases[line->canvas_index];
        fprintf(stream,
                "      {\"id\": \"%s\", \"type\": \"straight-line\", "
                "\"point_ids\": [\"%s\", \"%s\"], "
                "\"role\": \"%s\", \"canvas_id\": \"%s\"",
                line->id, world->points[line->a].id, world->points[line->b].id,
                line->kind == CF_LINE_BOUNDARY ?
                    "canvas-boundary" : "canvas-partition",
                canvas->id);
        if (line->partition_index >= 0) {
            fprintf(stream, ", \"partition_id\": \"%s\"",
                    world->partitions[(size_t)line->partition_index].id);
        }
        fprintf(stream, "}%s\n", i + 1U == world->line_count ? "" : ",");
    }
    fputs("    ]\n  },\n", stream);

    fputs("  \"canvases\": [\n", stream);
    for (i = 0U; i < world->canvas_count; ++i) {
        const cf_canvas *canvas = &world->canvases[i];
        fprintf(stream, "    {\"id\": \"%s\", \"point_ids\": [", canvas->id);
        for (j = 0U; j < canvas->point_count; ++j) {
            fprintf(stream, "\"%s\"%s", world->points[canvas->points[j]].id,
                    j + 1U == canvas->point_count ? "" : ", ");
        }
        fputs("], \"line_ids\": [", stream);
        for (j = 0U; j < canvas->line_count; ++j) {
            fprintf(stream, "\"%s\"%s", world->lines[canvas->lines[j]].id,
                    j + 1U == canvas->line_count ? "" : ", ");
        }
        fprintf(stream,
                "], \"bbox\": {\"min_x\": %lld, \"min_y\": %lld, "
                "\"max_x\": %lld, \"max_y\": %lld}, "
                "\"style\": {\"fill\": \"%s\", \"stroke\": \"%s\", "
                "\"stroke_width\": 2}}%s\n",
                (long long)canvas->min_x, (long long)canvas->min_y,
                (long long)canvas->max_x, (long long)canvas->max_y,
                canvas->fill, canvas->stroke,
                i + 1U == world->canvas_count ? "" : ",");
    }
    fputs("  ],\n", stream);

    fputs("  \"canvas_partitions\": [\n", stream);
    for (i = 0U; i < world->partition_count; ++i) {
        const cf_partition *partition = &world->partitions[i];
        fprintf(stream,
                "    {\"id\": \"%s\", \"canvas_id\": \"%s\", "
                "\"point_ids\": [\"%s\", \"%s\"], "
                "\"line_id\": \"%s\"}%s\n",
                partition->id,
                world->canvases[partition->canvas_index].id,
                world->points[partition->p1].id,
                world->points[partition->p2].id,
                world->lines[partition->line_index].id,
                i + 1U == world->partition_count ? "" : ",");
    }
    fputs("  ],\n", stream);

    fputs("  \"validation\": {\n"
          "    \"zero_collision\": true,\n"
          "    \"canvas_boundaries_closed\": true,\n"
          "    \"canvas_partitions_valid\": true,\n"
          "    \"numbers_are_rational\": true\n"
          "  }\n"
          "}\n", stream);
    return ferror(stream) == 0;
}

static bool cf_write_world(const cf_config *config, const cf_world *world) {
    FILE *stream;
    bool close_stream;
    bool ok;
    if (cf_ieq(config->output, "stdout") || strcmp(config->output, "-") == 0) {
        stream = stdout;
        close_stream = false;
    } else {
        stream = fopen(config->output, "w");
        if (stream == NULL) return false;
        close_stream = true;
    }
    ok = cf_write_json(stream, config, world);
    if (close_stream && fclose(stream) != 0) ok = false;
    return ok;
}

int main(int argc, char **argv) {
    cf_config config;
    cf_world world;
    bool should_run;
    int result = cf_parse_arguments(argc, argv, &config, &should_run);
    if (result != 0 || !should_run) return result;

    memset(&world, 0, sizeof(world));
    if (!cf_generate_world(&config, &world)) {
        fprintf(stderr, "world generation failed\n");
        cf_world_free(&world);
        return 1;
    }
    if (!cf_validate_world(&config, &world)) {
        fprintf(stderr, "generated world failed zero-collision validation\n");
        cf_world_free(&world);
        return 1;
    }
    if (!cf_write_world(&config, &world)) {
        perror("unable to write JSON world");
        cf_world_free(&world);
        return 1;
    }

    cf_world_free(&world);
    return 0;
}
