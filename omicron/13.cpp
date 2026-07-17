/*
 * 13.cpp
 *
 * Formal Book Sport Table generator for general-purpose Engineering Architecture.
 *
 * This program preserves the risk-free fabric utility pattern of 6(1).cpp:
 * explicit specs, config/direct/menu input, bounded execution, dry-run planning,
 * escaped source records, safe output, and deterministic record hashing.
 *
 * Enhancement:
 *   - Generates a static, formal Book Sport Table.
 *   - Row headings and column headings are fully configurable.
 *   - Headings are treated as pointers.
 *   - Pointers map to instructional semantic structures.
 *   - Cell records carry hard-barrier/deferred-acceptance metadata.
 *   - Dynamic Boolean truth arithmetic is intentionally deferred to 14.cpp.
 *
 * Build:
 *   c++ -std=c++17 -Wall -Wextra -pedantic -O2 13.cpp -o 13
 *
 * Examples:
 *   ./13 --sample-config book_sport_13.fabric
 *   ./13 --config book_sport_13.fabric
 *   ./13 --config book_sport_13.fabric --execute --overwrite
 *
 *   ./13 --table --execute --overwrite \
 *        --table-name engineering_architecture \
 *        --row-headings "x_state|x_material|x_force" \
 *        --column-headings "accept|reject|transform" \
 *        --semantic "x_state=Information state pointer" \
 *        --semantic "accept=Accepted transition operation" \
 *        --output-target engineering_book_sport_table.txt
 */

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr std::uint64_t kDefaultLimit = 10000;
constexpr std::uint64_t kUnapprovedRecordLimit = 100000;
constexpr std::uint64_t kMaxCartesianWidth = 64;
constexpr std::uint64_t kMaxRepeatCount = 1000000;
constexpr std::uint64_t kMaxHeadingCount = 100000;
constexpr std::size_t kMaxTextLength = 4096;
constexpr std::size_t kMaxSemanticLength = 16384;

enum class Flow {
    cartesian,
    literal,
    repeat,
    reverse
};

enum class WorkKind {
    object_fabric,
    book_sport_table
};

struct ObjectSpec {
    bool touched = false;
    std::string object_name = "x33";
    std::string input_name = "x1";
    std::string input_value = "0123456789";
    std::uint64_t input_width = 7;
    std::string flow_name = "x15";
    Flow flow = Flow::cartesian;
    std::string output_name = "x31";
    std::string output_target = "x33.cppdb.txt";
    std::string separator = "\n";
    std::string prefix;
    std::string suffix;
};

struct TableSpec {
    bool touched = false;
    std::string table_name = "book_sport_table";
    std::vector<std::string> row_headings;
    std::vector<std::string> column_headings;
    std::string heading_delimiter = "|";
    std::string row_role = "information_state_pointer";
    std::string column_role = "instructional_operation_pointer";
    std::string cell_role = "deferred_boolean_acceptance_cell";
    std::string output_name = "book_sport_table_output";
    std::string output_target = "book_sport_table.cppdb.txt";
    std::string separator = "\n";
    std::string boolean_engine = "14.cpp";
    std::string boolean_contract = "dynamic_boolean_truth_arithmetic";
    std::string barrier_policy = "hard_closed_until_boolean_acceptance";
    std::string acceptance_state = "deferred_to_14.cpp";
    std::string cell_pointer_prefix = "bs_cell";
    std::map<std::string, std::string> semantics;
};

struct WorkUnit {
    WorkKind kind = WorkKind::object_fabric;
    ObjectSpec object;
    TableSpec table;
};

struct Options {
    bool execute = false;
    bool allow_large = false;
    bool all = false;
    bool overwrite = false;
    bool menu = false;
    bool table_mode = false;
    std::uint64_t start = 0;
    std::uint64_t limit = kDefaultLimit;
    std::string config_path;
    std::string sample_config_path;
};

struct Program {
    Options options;
    ObjectSpec direct_object;
    TableSpec direct_table;
    bool has_direct_object = false;
    bool has_direct_table = false;
};

class OutputSink {
public:
    virtual ~OutputSink() = default;
    virtual void write(std::string_view value) = 0;
};

class StreamSink final : public OutputSink {
public:
    explicit StreamSink(std::ostream& stream) : stream_(stream) {}

    void write(std::string_view value) override {
        stream_.write(value.data(), static_cast<std::streamsize>(value.size()));
        if (!stream_) {
            throw std::runtime_error("Failed while writing to stream.");
        }
    }

private:
    std::ostream& stream_;
};

class FileSink final : public OutputSink {
public:
    FileSink(const std::string& path, const char* mode) : file_(std::fopen(path.c_str(), mode)) {
        if (file_ == nullptr) {
            throw std::runtime_error("Unable to open output file: " + path);
        }
    }

    ~FileSink() override {
        if (file_ != nullptr) {
            std::fclose(file_);
        }
    }

    FileSink(const FileSink&) = delete;
    FileSink& operator=(const FileSink&) = delete;

    void write(std::string_view value) override {
        if (!value.empty() &&
            std::fwrite(value.data(), 1, value.size(), file_) != value.size()) {
            throw std::runtime_error("Failed while writing output file.");
        }
    }

private:
    std::FILE* file_;
};

class InputFile {
public:
    explicit InputFile(const std::string& path) : file_(std::fopen(path.c_str(), "rb")) {
        if (file_ == nullptr) {
            throw std::runtime_error("Unable to open input file: " + path);
        }
    }

    ~InputFile() {
        if (file_ != nullptr) {
            std::fclose(file_);
        }
    }

    InputFile(const InputFile&) = delete;
    InputFile& operator=(const InputFile&) = delete;

    bool read_line(std::string& line) {
        char buffer[8192];
        line.clear();

        for (;;) {
            if (std::fgets(buffer, sizeof(buffer), file_) == nullptr) {
                if (std::ferror(file_) != 0) {
                    throw std::runtime_error("Failed while reading input file.");
                }
                return !line.empty();
            }

            line += buffer;
            if (!line.empty() && line.back() == '\n') {
                break;
            }

            const std::size_t chunk_size = std::char_traits<char>::length(buffer);
            if (chunk_size + 1 < sizeof(buffer)) {
                break;
            }
        }

        while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) {
            line.pop_back();
        }

        return true;
    }

private:
    std::FILE* file_;
};

class Writer {
public:
    explicit Writer(OutputSink& sink) : sink_(sink) {}

    Writer& operator<<(char value) {
        sink_.write(std::string_view(&value, 1));
        return *this;
    }

    Writer& operator<<(std::string_view value) {
        sink_.write(value);
        return *this;
    }

    Writer& operator<<(const std::string& value) {
        sink_.write(value);
        return *this;
    }

    Writer& operator<<(const char* value) {
        sink_.write(value == nullptr ? std::string_view{} : std::string_view(value));
        return *this;
    }

    template <typename T>
    Writer& operator<<(const T& value) {
        std::ostringstream out;
        out << value;
        sink_.write(out.str());
        return *this;
    }

private:
    OutputSink& sink_;
};

std::string to_lower(std::string value) {
    for (char& c : value) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return value;
}

std::string trim(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front()))) {
        value.erase(value.begin());
    }
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) {
        value.pop_back();
    }
    return value;
}

bool equals_ignore_case(std::string_view lhs, std::string_view rhs) {
    if (lhs.size() != rhs.size()) {
        return false;
    }

    for (std::size_t i = 0; i < lhs.size(); ++i) {
        if (std::tolower(static_cast<unsigned char>(lhs[i])) !=
            std::tolower(static_cast<unsigned char>(rhs[i]))) {
            return false;
        }
    }

    return true;
}

bool parse_u64(std::string_view text, std::uint64_t& out) {
    if (text.empty()) {
        return false;
    }

    std::uint64_t value = 0;
    for (char c : text) {
        if (!std::isdigit(static_cast<unsigned char>(c))) {
            return false;
        }
        const std::uint64_t digit = static_cast<std::uint64_t>(c - '0');
        if (value > (std::numeric_limits<std::uint64_t>::max() - digit) / 10) {
            return false;
        }
        value = value * 10 + digit;
    }

    out = value;
    return true;
}

std::uint64_t require_u64(const std::vector<std::string>& args, std::size_t& i) {
    if (i + 1 >= args.size()) {
        throw std::runtime_error("Missing value for " + args[i]);
    }

    std::uint64_t value = 0;
    if (!parse_u64(args[++i], value)) {
        throw std::runtime_error("Invalid unsigned integer for " + args[i - 1] + ": " + args[i]);
    }
    return value;
}

std::string require_string(const std::vector<std::string>& args, std::size_t& i) {
    if (i + 1 >= args.size()) {
        throw std::runtime_error("Missing value for " + args[i]);
    }
    return args[++i];
}

bool safe_power(std::uint64_t base, std::uint64_t exp, std::uint64_t& out) {
    if (base == 0) {
        return false;
    }

    std::uint64_t value = 1;
    for (std::uint64_t i = 0; i < exp; ++i) {
        if (value > std::numeric_limits<std::uint64_t>::max() / base) {
            return false;
        }
        value *= base;
    }

    out = value;
    return true;
}

bool safe_mul(std::uint64_t a, std::uint64_t b, std::uint64_t& out) {
    if (a != 0 && b > std::numeric_limits<std::uint64_t>::max() / a) {
        return false;
    }
    out = a * b;
    return true;
}

std::string unescape_text(std::string_view value) {
    std::string out;
    out.reserve(value.size());

    for (std::size_t i = 0; i < value.size(); ++i) {
        char c = value[i];
        if (c != '\\' || i + 1 >= value.size()) {
            out.push_back(c);
            continue;
        }

        const char next = value[++i];
        if (next == 'n') {
            out.push_back('\n');
        } else if (next == 't') {
            out.push_back('\t');
        } else if (next == 'r') {
            out.push_back('\r');
        } else if (next == '\\') {
            out.push_back('\\');
        } else {
            out.push_back(next);
        }
    }

    return out;
}

std::string escape_field(std::string_view value) {
    std::ostringstream out;
    out << std::hex << std::uppercase << std::setfill('0');

    for (unsigned char c : value) {
        if (c == '\\') {
            out << "\\\\";
        } else if (c == '\n') {
            out << "\\n";
        } else if (c == '\r') {
            out << "\\r";
        } else if (c == '\t') {
            out << "\\t";
        } else if (c < 32 || c == 127) {
            out << "\\x" << std::setw(2) << static_cast<unsigned int>(c);
        } else {
            out << static_cast<char>(c);
        }
    }

    return out.str();
}

std::uint64_t fnv1a_64(std::string_view value) {
    std::uint64_t hash = 14695981039346656037ull;
    for (unsigned char c : value) {
        hash ^= static_cast<std::uint64_t>(c);
        hash *= 1099511628211ull;
    }
    return hash;
}

std::string hex64(std::uint64_t value) {
    std::ostringstream out;
    out << std::hex << std::nouppercase << std::setfill('0') << std::setw(16) << value;
    return out.str();
}

std::string flow_name(Flow flow) {
    if (flow == Flow::cartesian) {
        return "cartesian";
    }
    if (flow == Flow::literal) {
        return "literal";
    }
    if (flow == Flow::repeat) {
        return "repeat";
    }
    return "reverse";
}

Flow parse_flow(std::string_view value) {
    const std::string normalized = to_lower(std::string(value));
    if (normalized == "cartesian" || normalized == "product" || normalized == "combinations") {
        return Flow::cartesian;
    }
    if (normalized == "literal" || normalized == "echo") {
        return Flow::literal;
    }
    if (normalized == "repeat") {
        return Flow::repeat;
    }
    if (normalized == "reverse") {
        return Flow::reverse;
    }
    throw std::runtime_error("Unknown flow_type: " + std::string(value));
}

std::vector<std::string> split_text(std::string_view value, std::string_view delimiter) {
    if (delimiter.empty()) {
        throw std::runtime_error("Delimiter cannot be empty.");
    }

    std::vector<std::string> parts;
    std::size_t pos = 0;
    while (pos <= value.size()) {
        const std::size_t next = value.find(delimiter, pos);
        const std::size_t end = next == std::string_view::npos ? value.size() : next;
        std::string token(value.substr(pos, end - pos));
        token = trim(unescape_text(token));
        if (!token.empty()) {
            parts.push_back(token);
        }
        if (next == std::string_view::npos) {
            break;
        }
        pos = next + delimiter.size();
    }
    return parts;
}

std::pair<std::string, std::string> split_semantic_assignment(std::string value) {
    const std::size_t arrow = value.find("=>");
    if (arrow != std::string::npos) {
        return {trim(value.substr(0, arrow)), trim(value.substr(arrow + 2))};
    }

    const std::size_t equals = value.find('=');
    if (equals != std::string::npos) {
        return {trim(value.substr(0, equals)), trim(value.substr(equals + 1))};
    }

    throw std::runtime_error("Semantic mapping must use pointer=semantic or pointer=>semantic: " + value);
}

void add_semantic(TableSpec& spec, const std::string& assignment) {
    const auto parsed = split_semantic_assignment(assignment);
    if (parsed.first.empty()) {
        throw std::runtime_error("Semantic pointer cannot be empty.");
    }
    if (parsed.second.size() > kMaxSemanticLength) {
        throw std::runtime_error("Semantic structure is too large for pointer: " + parsed.first);
    }
    spec.semantics[parsed.first] = unescape_text(parsed.second);
}

void load_headings_file(const std::string& path,
                        std::vector<std::string>& headings,
                        std::map<std::string, std::string>& semantics) {
    InputFile in(path);
    std::string line;
    std::uint64_t line_number = 0;

    while (in.read_line(line)) {
        ++line_number;
        std::string raw = trim(line);
        if (raw.empty()) {
            continue;
        }

        if (raw.size() >= 1 && raw[0] == '#') {
            continue;
        }

        try {
            if (raw.find("=>") != std::string::npos || raw.find('=') != std::string::npos) {
                const auto parsed = split_semantic_assignment(raw);
                if (parsed.first.empty()) {
                    throw std::runtime_error("Empty heading pointer.");
                }
                headings.push_back(unescape_text(parsed.first));
                semantics[unescape_text(parsed.first)] = unescape_text(parsed.second);
            } else {
                headings.push_back(unescape_text(raw));
            }
        } catch (const std::exception& ex) {
            std::ostringstream message;
            message << "Heading file " << path << " line " << line_number << ": " << ex.what();
            throw std::runtime_error(message.str());
        }
    }
}

void load_semantics_file(const std::string& path, TableSpec& spec) {
    InputFile in(path);
    std::string line;
    std::uint64_t line_number = 0;

    while (in.read_line(line)) {
        ++line_number;
        std::string raw = trim(line);
        if (raw.empty() || (!raw.empty() && raw[0] == '#')) {
            continue;
        }

        try {
            add_semantic(spec, raw);
        } catch (const std::exception& ex) {
            std::ostringstream message;
            message << "Semantics file " << path << " line " << line_number << ": " << ex.what();
            throw std::runtime_error(message.str());
        }
    }
}

std::string make_cartesian_value(std::uint64_t ordinal,
                                 std::uint64_t width,
                                 std::string_view alphabet) {
    std::string value(static_cast<std::size_t>(width), '\0');
    const std::uint64_t base = static_cast<std::uint64_t>(alphabet.size());

    for (std::uint64_t pos = 0; pos < width; ++pos) {
        const std::uint64_t reversed_index = width - 1 - pos;
        const std::uint64_t alphabet_index = ordinal % base;
        value[static_cast<std::size_t>(reversed_index)] = alphabet[static_cast<std::size_t>(alphabet_index)];
        ordinal /= base;
    }

    return value;
}

std::string make_payload(const ObjectSpec& spec, std::uint64_t ordinal) {
    if (spec.flow == Flow::cartesian) {
        return make_cartesian_value(ordinal, spec.input_width, spec.input_value);
    }
    if (spec.flow == Flow::literal) {
        return spec.input_value;
    }
    if (spec.flow == Flow::repeat) {
        return spec.input_value;
    }

    std::string reversed = spec.input_value;
    std::reverse(reversed.begin(), reversed.end());
    return reversed;
}

std::uint64_t expected_total(const ObjectSpec& spec) {
    if (spec.flow == Flow::cartesian) {
        std::uint64_t total = 0;
        if (!safe_power(static_cast<std::uint64_t>(spec.input_value.size()),
                        spec.input_width,
                        total)) {
            throw std::runtime_error("Combination count overflowed uint64_t for " +
                                     spec.object_name);
        }
        return total;
    }

    if (spec.flow == Flow::repeat) {
        return spec.input_width;
    }

    return 1;
}

std::uint64_t expected_total(const TableSpec& spec) {
    std::uint64_t total = 0;
    if (!safe_mul(static_cast<std::uint64_t>(spec.row_headings.size()),
                  static_cast<std::uint64_t>(spec.column_headings.size()),
                  total)) {
        throw std::runtime_error("Book Sport table cell count overflowed uint64_t for " +
                                 spec.table_name);
    }
    return total;
}

std::uint64_t requested_count(const Options& options, std::uint64_t total) {
    if (options.start >= total) {
        return 0;
    }

    const std::uint64_t remaining = total - options.start;
    return options.all || options.limit > remaining ? remaining : options.limit;
}

bool file_exists(const std::string& path) {
    std::FILE* file = std::fopen(path.c_str(), "rb");
    if (file == nullptr) {
        return false;
    }
    std::fclose(file);
    return true;
}

void validate_text_length(const std::string& label, const std::string& value) {
    if (value.size() > kMaxTextLength) {
        throw std::runtime_error(label + " is too large; maximum length is 4096 bytes.");
    }
}

void validate_no_duplicates(const std::vector<std::string>& values, const std::string& label) {
    std::set<std::string> seen;
    for (const std::string& value : values) {
        if (!seen.insert(value).second) {
            throw std::runtime_error(label + " contains duplicate pointer: " + value);
        }
    }
}

void validate_spec(const ObjectSpec& spec) {
    if (spec.object_name.empty() || spec.input_name.empty() || spec.flow_name.empty() ||
        spec.output_name.empty() || spec.output_target.empty()) {
        throw std::runtime_error("Object spec has an empty required name or output target.");
    }

    validate_text_length("input_value", spec.input_value);
    validate_text_length("prefix", spec.prefix);
    validate_text_length("suffix", spec.suffix);
    validate_text_length("separator", spec.separator);

    if (spec.input_width == 0) {
        throw std::runtime_error("input_width must be greater than zero for " + spec.object_name);
    }

    if (spec.flow == Flow::cartesian) {
        if (spec.input_value.empty()) {
            throw std::runtime_error("cartesian input_value cannot be empty for " + spec.object_name);
        }
        if (spec.input_width > kMaxCartesianWidth) {
            throw std::runtime_error("cartesian input_width exceeds 64 for " + spec.object_name);
        }
        (void)expected_total(spec);
    }

    if (spec.flow == Flow::repeat && spec.input_width > kMaxRepeatCount) {
        throw std::runtime_error("repeat input_width exceeds 1000000 for " + spec.object_name);
    }
}

void validate_spec(const TableSpec& spec) {
    if (spec.table_name.empty() || spec.output_name.empty() || spec.output_target.empty()) {
        throw std::runtime_error("Table spec has an empty required name or output target.");
    }

    validate_text_length("table_name", spec.table_name);
    validate_text_length("row_role", spec.row_role);
    validate_text_length("column_role", spec.column_role);
    validate_text_length("cell_role", spec.cell_role);
    validate_text_length("output_name", spec.output_name);
    validate_text_length("output_target", spec.output_target);
    validate_text_length("separator", spec.separator);
    validate_text_length("boolean_engine", spec.boolean_engine);
    validate_text_length("boolean_contract", spec.boolean_contract);
    validate_text_length("barrier_policy", spec.barrier_policy);
    validate_text_length("acceptance_state", spec.acceptance_state);
    validate_text_length("cell_pointer_prefix", spec.cell_pointer_prefix);

    if (spec.row_headings.empty()) {
        throw std::runtime_error("Book Sport table requires at least one row heading pointer.");
    }
    if (spec.column_headings.empty()) {
        throw std::runtime_error("Book Sport table requires at least one column heading pointer.");
    }
    if (spec.row_headings.size() > kMaxHeadingCount) {
        throw std::runtime_error("Too many row headings; maximum is 100000.");
    }
    if (spec.column_headings.size() > kMaxHeadingCount) {
        throw std::runtime_error("Too many column headings; maximum is 100000.");
    }

    for (const std::string& row : spec.row_headings) {
        if (trim(row).empty()) {
            throw std::runtime_error("Row heading pointer cannot be empty.");
        }
        validate_text_length("row heading pointer", row);
    }
    for (const std::string& column : spec.column_headings) {
        if (trim(column).empty()) {
            throw std::runtime_error("Column heading pointer cannot be empty.");
        }
        validate_text_length("column heading pointer", column);
    }
    for (const auto& item : spec.semantics) {
        validate_text_length("semantic pointer", item.first);
        if (item.second.size() > kMaxSemanticLength) {
            throw std::runtime_error("Semantic structure too large for pointer: " + item.first);
        }
    }

    validate_no_duplicates(spec.row_headings, "Row headings");
    validate_no_duplicates(spec.column_headings, "Column headings");
    (void)expected_total(spec);
}

void validate_safety(const Options& options,
                     const std::string& name,
                     std::uint64_t count) {
    if (!options.allow_large && count > kUnapprovedRecordLimit) {
        throw std::runtime_error("Refusing to emit more than 100000 records for " +
                                 name + " without --allow-large.");
    }
}

void set_object_value(ObjectSpec& spec, std::string key, std::string value) {
    key = to_lower(trim(key));
    value = trim(value);
    spec.touched = true;

    if (key == "object" || key == "object_name" || key == "name") {
        spec.object_name = value;
    } else if (key == "input_name") {
        spec.input_name = value;
    } else if (key == "input" || key == "input_value" || key == "alphabet") {
        spec.input_value = unescape_text(value);
    } else if (key == "input_width" || key == "width" || key == "length" || key == "depth") {
        if (!parse_u64(value, spec.input_width)) {
            throw std::runtime_error("Invalid input_width: " + value);
        }
    } else if (key == "flow_name") {
        spec.flow_name = value;
    } else if (key == "flow" || key == "flow_type" || key == "processing_flow") {
        spec.flow = parse_flow(value);
    } else if (key == "output_name") {
        spec.output_name = value;
    } else if (key == "output" || key == "output_target" || key == "file") {
        spec.output_target = value;
    } else if (key == "separator" || key == "sep") {
        spec.separator = unescape_text(value);
    } else if (key == "prefix") {
        spec.prefix = unescape_text(value);
    } else if (key == "suffix") {
        spec.suffix = unescape_text(value);
    } else {
        throw std::runtime_error("Unknown object config key: " + key);
    }
}

void set_table_value(TableSpec& spec, std::string key, std::string value) {
    key = to_lower(trim(key));
    value = trim(value);
    spec.touched = true;

    if (key == "table" || key == "table_name" || key == "name") {
        spec.table_name = value;
    } else if (key == "row_headings" || key == "rows" || key == "row_pointers") {
        spec.row_headings = split_text(value, spec.heading_delimiter);
    } else if (key == "column_headings" || key == "columns" || key == "column_pointers" || key == "cols") {
        spec.column_headings = split_text(value, spec.heading_delimiter);
    } else if (key == "heading_delimiter" || key == "delimiter") {
        spec.heading_delimiter = unescape_text(value);
        if (spec.heading_delimiter.empty()) {
            throw std::runtime_error("heading_delimiter cannot be empty.");
        }
    } else if (key == "row_file" || key == "row_headings_file" || key == "rows_file") {
        load_headings_file(value, spec.row_headings, spec.semantics);
    } else if (key == "column_file" || key == "column_headings_file" || key == "columns_file" || key == "cols_file") {
        load_headings_file(value, spec.column_headings, spec.semantics);
    } else if (key == "semantics_file" || key == "semantic_file") {
        load_semantics_file(value, spec);
    } else if (key == "semantic" || key == "semantics" || key == "map" || key == "pointer_map") {
        add_semantic(spec, value);
    } else if (key == "row_role") {
        spec.row_role = value;
    } else if (key == "column_role" || key == "col_role") {
        spec.column_role = value;
    } else if (key == "cell_role") {
        spec.cell_role = value;
    } else if (key == "output_name") {
        spec.output_name = value;
    } else if (key == "output" || key == "output_target" || key == "file") {
        spec.output_target = value;
    } else if (key == "separator" || key == "sep") {
        spec.separator = unescape_text(value);
    } else if (key == "boolean_engine" || key == "bool_engine") {
        spec.boolean_engine = value;
    } else if (key == "boolean_contract" || key == "bool_contract" || key == "contract") {
        spec.boolean_contract = value;
    } else if (key == "barrier_policy" || key == "barrier" || key == "hard_barrier") {
        spec.barrier_policy = value;
    } else if (key == "acceptance_state" || key == "acceptance") {
        spec.acceptance_state = value;
    } else if (key == "cell_pointer_prefix" || key == "cell_prefix") {
        spec.cell_pointer_prefix = value;
    } else {
        throw std::runtime_error("Unknown table config key: " + key);
    }
}

bool parse_config_line(std::string line, std::string& key, std::string& value) {
    const std::size_t comment = line.find('#');
    if (comment != std::string::npos) {
        line.erase(comment);
    }

    line = trim(line);
    if (line.empty()) {
        return false;
    }

    const std::size_t equals = line.find('=');
    if (equals != std::string::npos) {
        key = trim(line.substr(0, equals));
        value = trim(line.substr(equals + 1));
        return !key.empty();
    }

    std::istringstream in(line);
    in >> key;
    std::getline(in, value);
    value = trim(value);
    return !key.empty();
}

bool is_table_key(std::string key) {
    key = to_lower(trim(key));
    return key == "table" || key == "table_name" || key == "row_headings" ||
           key == "rows" || key == "row_pointers" || key == "column_headings" ||
           key == "columns" || key == "column_pointers" || key == "cols" ||
           key == "heading_delimiter" || key == "delimiter" || key == "row_file" ||
           key == "row_headings_file" || key == "rows_file" || key == "column_file" ||
           key == "column_headings_file" || key == "columns_file" || key == "cols_file" ||
           key == "semantic" || key == "semantics" || key == "semantics_file" ||
           key == "semantic_file" || key == "map" || key == "pointer_map" ||
           key == "row_role" || key == "column_role" || key == "col_role" ||
           key == "cell_role" || key == "boolean_engine" || key == "bool_engine" ||
           key == "boolean_contract" || key == "bool_contract" || key == "contract" ||
           key == "barrier_policy" || key == "barrier" || key == "hard_barrier" ||
           key == "acceptance_state" || key == "acceptance" ||
           key == "cell_pointer_prefix" || key == "cell_prefix";
}

void finalize_work_unit(std::vector<WorkUnit>& units, WorkUnit& current, bool& touched) {
    if (!touched) {
        return;
    }

    if (current.kind == WorkKind::book_sport_table) {
        validate_spec(current.table);
    } else {
        validate_spec(current.object);
    }

    units.push_back(current);
    current = WorkUnit{};
    touched = false;
}

std::vector<WorkUnit> load_config(const std::string& path) {
    InputFile in(path);
    std::vector<WorkUnit> units;
    WorkUnit current;
    bool touched = false;
    std::string line;
    std::uint64_t line_number = 0;

    while (in.read_line(line)) {
        ++line_number;

        std::string key;
        std::string value;
        if (!parse_config_line(line, key, value)) {
            continue;
        }

        if (equals_ignore_case(key, "end")) {
            finalize_work_unit(units, current, touched);
            continue;
        }

        const std::string normalized_key = to_lower(trim(key));
        const std::string normalized_value = to_lower(trim(value));

        if (normalized_key == "kind" || normalized_key == "type" || normalized_key == "mode") {
            if (touched) {
                finalize_work_unit(units, current, touched);
            }
            if (normalized_value == "table" || normalized_value == "book_sport_table" ||
                normalized_value == "booksport") {
                current.kind = WorkKind::book_sport_table;
                current.table.touched = true;
            } else if (normalized_value == "object" || normalized_value == "fabric" ||
                       normalized_value == "object_fabric") {
                current.kind = WorkKind::object_fabric;
                current.object.touched = true;
            } else {
                throw std::runtime_error("Config line " + std::to_string(line_number) +
                                         ": unknown kind/type/mode: " + value);
            }
            touched = true;
            continue;
        }

        try {
            if (!touched) {
                current.kind = is_table_key(key) ? WorkKind::book_sport_table : WorkKind::object_fabric;
                touched = true;
            }

            if (current.kind == WorkKind::book_sport_table) {
                set_table_value(current.table, key, value);
            } else {
                set_object_value(current.object, key, value);
            }
        } catch (const std::exception& ex) {
            std::ostringstream message;
            message << "Config line " << line_number << ": " << ex.what();
            throw std::runtime_error(message.str());
        }
    }

    finalize_work_unit(units, current, touched);

    if (units.empty()) {
        throw std::runtime_error("Config file contains no specs: " + path);
    }

    return units;
}

void write_sample_config(const std::string& path, bool overwrite) {
    if (!overwrite && file_exists(path)) {
        throw std::runtime_error("Sample config already exists. Use --overwrite to replace it: " + path);
    }

    FileSink sink(path, "wb");
    Writer out(sink);
    out
        << "# 13.cpp formal Book Sport Table config\n"
        << "# Dynamic Boolean arithmetic is deferred to 14.cpp.\n"
        << "\n"
        << "kind=table\n"
        << "table_name=engineering_architecture_book_sport\n"
        << "heading_delimiter=|\n"
        << "row_headings=x_state|x_material|x_force|x_boundary|x_measurement|x_accepted_information\n"
        << "column_headings=observe|classify|validate|transform|compose|barrier_check\n"
        << "semantic=x_state=>Pointer to a declared information state.\n"
        << "semantic=x_material=>Pointer to a material, component, or resource state.\n"
        << "semantic=x_force=>Pointer to a force, constraint, load, or action.\n"
        << "semantic=x_boundary=>Pointer to a hard boundary condition.\n"
        << "semantic=x_measurement=>Pointer to a measured engineering datum.\n"
        << "semantic=x_accepted_information=>Pointer to accepted information after Boolean contract approval.\n"
        << "semantic=observe=>Instruction pointer for observation and state capture.\n"
        << "semantic=classify=>Instruction pointer for type classification.\n"
        << "semantic=validate=>Instruction pointer for Boolean contract validation.\n"
        << "semantic=transform=>Instruction pointer for accepted state transition.\n"
        << "semantic=compose=>Instruction pointer for recursive operation composition.\n"
        << "semantic=barrier_check=>Instruction pointer for hard-barrier enforcement.\n"
        << "row_role=engineering_information_state_pointer\n"
        << "column_role=engineering_instruction_pointer\n"
        << "cell_role=static_deferred_acceptance_contract_cell\n"
        << "boolean_engine=14.cpp\n"
        << "boolean_contract=dynamic_boolean_truth_arithmetic\n"
        << "barrier_policy=hard_closed_until_boolean_acceptance\n"
        << "acceptance_state=deferred_to_14.cpp\n"
        << "cell_pointer_prefix=bs_cell\n"
        << "output_name=book_sport_static_table\n"
        << "output_target=engineering_architecture_book_sport.table.txt\n"
        << "separator=\\n\n"
        << "end\n"
        << "\n"
        << "# Original object-fabric mode retained from 6(1).cpp style.\n"
        << "kind=object\n"
        << "object_name=x33\n"
        << "input_name=x1\n"
        << "input_value=0123456789\n"
        << "input_width=3\n"
        << "flow_name=x15\n"
        << "flow_type=cartesian\n"
        << "output_name=x31\n"
        << "output_target=x33.cppdb.txt\n"
        << "separator=\\n\n"
        << "prefix=\n"
        << "suffix=\n"
        << "end\n";
}

std::string prompt_string(const std::string& label, const std::string& default_value) {
    std::cout << label << " [" << escape_field(default_value) << "]: ";
    std::string value;
    std::getline(std::cin, value);
    return value.empty() ? default_value : value;
}

std::uint64_t prompt_u64(const std::string& label, std::uint64_t default_value) {
    for (;;) {
        std::cout << label << " [" << default_value << "]: ";
        std::string value;
        std::getline(std::cin, value);
        if (value.empty()) {
            return default_value;
        }

        std::uint64_t parsed = 0;
        if (parse_u64(value, parsed)) {
            return parsed;
        }

        std::cout << "Please enter a non-negative integer.\n";
    }
}

ObjectSpec prompt_object_spec() {
    ObjectSpec spec;
    spec.object_name = prompt_string("object_name", spec.object_name);
    spec.input_name = prompt_string("input_name", spec.input_name);
    spec.input_value = unescape_text(prompt_string("input_value", spec.input_value));
    spec.input_width = prompt_u64("input_width", spec.input_width);
    spec.flow_name = prompt_string("flow_name", spec.flow_name);
    spec.flow = parse_flow(prompt_string("flow_type cartesian|literal|repeat|reverse", "cartesian"));
    spec.output_name = prompt_string("output_name", spec.output_name);
    spec.output_target = prompt_string("output_target file|stdout|-", spec.output_target);
    spec.separator = unescape_text(prompt_string("separator", "\\n"));
    spec.prefix = unescape_text(prompt_string("prefix", ""));
    spec.suffix = unescape_text(prompt_string("suffix", ""));
    spec.touched = true;
    validate_spec(spec);
    return spec;
}

TableSpec prompt_table_spec() {
    TableSpec spec;
    spec.table_name = prompt_string("table_name", spec.table_name);
    spec.heading_delimiter = unescape_text(prompt_string("heading_delimiter", spec.heading_delimiter));
    spec.row_headings = split_text(prompt_string("row_headings", "x_state|x_material|x_force"),
                                   spec.heading_delimiter);
    spec.column_headings = split_text(prompt_string("column_headings", "observe|validate|transform"),
                                      spec.heading_delimiter);
    spec.row_role = prompt_string("row_role", spec.row_role);
    spec.column_role = prompt_string("column_role", spec.column_role);
    spec.cell_role = prompt_string("cell_role", spec.cell_role);
    spec.boolean_engine = prompt_string("boolean_engine", spec.boolean_engine);
    spec.boolean_contract = prompt_string("boolean_contract", spec.boolean_contract);
    spec.barrier_policy = prompt_string("barrier_policy", spec.barrier_policy);
    spec.acceptance_state = prompt_string("acceptance_state", spec.acceptance_state);
    spec.output_name = prompt_string("output_name", spec.output_name);
    spec.output_target = prompt_string("output_target file|stdout|-", spec.output_target);
    spec.separator = unescape_text(prompt_string("separator", "\\n"));
    spec.touched = true;
    validate_spec(spec);
    return spec;
}

void print_help(const char* executable) {
    std::cout
        << "Usage:\n"
        << "  " << executable << " --menu [--table]\n"
        << "  " << executable << " --config <path> [--execute]\n"
        << "  " << executable << " --sample-config <path>\n"
        << "  " << executable << " --table [table flags] [--execute]\n"
        << "  " << executable << " [object flags] [--execute]\n\n"
        << "Table flags for formal Book Sport Table generation:\n"
        << "  --table                         direct table mode\n"
        << "  --table-name <name>             table identity name\n"
        << "  --heading-delimiter <text>      delimiter for heading lists, default |\n"
        << "  --row-headings <list>           row pointer list, e.g. x1|x2|x3\n"
        << "  --column-headings <list>        column pointer list, e.g. accept|reject\n"
        << "  --row-headings-file <path>      one row pointer per line, or pointer=semantic\n"
        << "  --column-headings-file <path>   one column pointer per line, or pointer=semantic\n"
        << "  --semantic <pointer=structure>  map pointer to instructional semantics\n"
        << "  --semantics-file <path>         pointer=semantic mappings\n"
        << "  --row-role <text>               row role metadata\n"
        << "  --column-role <text>            column role metadata\n"
        << "  --cell-role <text>              cell role metadata\n"
        << "  --boolean-engine <path>         dynamic Boolean engine ref, default 14.cpp\n"
        << "  --boolean-contract <name>       Boolean contract name\n"
        << "  --barrier-policy <text>         hard-barrier policy\n"
        << "  --acceptance-state <text>       default acceptance state\n"
        << "  --cell-pointer-prefix <text>    cell pointer prefix\n\n"
        << "Object fabric flags retained from 6(1).cpp-style utility:\n"
        << "  --object-name <name>       runtime object name\n"
        << "  --input-name <name>        runtime input name\n"
        << "  --input-value <value>      payload/alphabet, supports \\\\n, \\\\t, \\\\r\n"
        << "  --input-width <n>          width/count/depth\n"
        << "  --flow-name <name>         runtime processing-flow name\n"
        << "  --flow-type <type>         cartesian|literal|repeat|reverse\n"
        << "  --output-name <name>       runtime output name\n"
        << "  --output-target <target>   file path, stdout, or -\n"
        << "  --separator <text>         stored as metadata, supports escapes\n"
        << "  --prefix <text>            prepended to rendered value\n"
        << "  --suffix <text>            appended to rendered value\n\n"
        << "Execution controls:\n"
        << "  --start <n>                first cell/record ordinal, default 0\n"
        << "  --limit <n>                maximum emitted cells/records, default 10000\n"
        << "  --all                      emit all cells/records after --start\n"
        << "  --allow-large              allow more than 100000 emitted records\n"
        << "  --overwrite                allow replacing output files\n"
        << "  --execute                  actually write output\n\n"
        << "Aliases:\n"
        << "  -n <name>  -i <value>  -w <n>  -f <type>  -o <target>\n";
}

Program parse_program(int argc, char** argv) {
    Program program;
    std::vector<std::string> args(argv, argv + argc);

    for (std::size_t i = 1; i < args.size(); ++i) {
        const std::string& arg = args[i];

        if (arg == "--help" || arg == "-h") {
            print_help(argv[0]);
            std::exit(0);
        } else if (arg == "--execute") {
            program.options.execute = true;
        } else if (arg == "--allow-large") {
            program.options.allow_large = true;
        } else if (arg == "--all") {
            program.options.all = true;
        } else if (arg == "--overwrite") {
            program.options.overwrite = true;
        } else if (arg == "--menu" || arg == "--ui") {
            program.options.menu = true;
        } else if (arg == "--table" || arg == "--book-sport-table") {
            program.options.table_mode = true;
            program.has_direct_table = true;
            program.direct_table.touched = true;
        } else if (arg == "--start") {
            program.options.start = require_u64(args, i);
        } else if (arg == "--limit") {
            program.options.limit = require_u64(args, i);
        } else if (arg == "--config") {
            program.options.config_path = require_string(args, i);
        } else if (arg == "--sample-config") {
            program.options.sample_config_path = require_string(args, i);

        } else if (arg == "--table-name") {
            set_table_value(program.direct_table, "table_name", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--heading-delimiter") {
            set_table_value(program.direct_table, "heading_delimiter", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--row-headings" || arg == "--rows") {
            set_table_value(program.direct_table, "row_headings", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--column-headings" || arg == "--columns" || arg == "--cols") {
            set_table_value(program.direct_table, "column_headings", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--row-headings-file" || arg == "--row-file") {
            set_table_value(program.direct_table, "row_headings_file", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--column-headings-file" || arg == "--column-file") {
            set_table_value(program.direct_table, "column_headings_file", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--semantic") {
            set_table_value(program.direct_table, "semantic", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--semantics-file") {
            set_table_value(program.direct_table, "semantics_file", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--row-role") {
            set_table_value(program.direct_table, "row_role", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--column-role" || arg == "--col-role") {
            set_table_value(program.direct_table, "column_role", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--cell-role") {
            set_table_value(program.direct_table, "cell_role", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--boolean-engine") {
            set_table_value(program.direct_table, "boolean_engine", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--boolean-contract") {
            set_table_value(program.direct_table, "boolean_contract", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--barrier-policy") {
            set_table_value(program.direct_table, "barrier_policy", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--acceptance-state") {
            set_table_value(program.direct_table, "acceptance_state", require_string(args, i));
            program.has_direct_table = true;
        } else if (arg == "--cell-pointer-prefix") {
            set_table_value(program.direct_table, "cell_pointer_prefix", require_string(args, i));
            program.has_direct_table = true;

        } else if (arg == "--object-name" || arg == "-n") {
            set_object_value(program.direct_object, "object_name", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--input-name") {
            set_object_value(program.direct_object, "input_name", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--input-value" || arg == "-i") {
            set_object_value(program.direct_object, "input_value", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--input-width" || arg == "-w") {
            set_object_value(program.direct_object, "input_width", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--flow-name") {
            set_object_value(program.direct_object, "flow_name", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--flow-type" || arg == "-f") {
            set_object_value(program.direct_object, "flow_type", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--output-name") {
            if (program.options.table_mode || program.has_direct_table) {
                set_table_value(program.direct_table, "output_name", require_string(args, i));
                program.has_direct_table = true;
            } else {
                set_object_value(program.direct_object, "output_name", require_string(args, i));
                program.has_direct_object = true;
            }
        } else if (arg == "--output-target" || arg == "-o") {
            if (program.options.table_mode || program.has_direct_table) {
                set_table_value(program.direct_table, "output_target", require_string(args, i));
                program.has_direct_table = true;
            } else {
                set_object_value(program.direct_object, "output_target", require_string(args, i));
                program.has_direct_object = true;
            }
        } else if (arg == "--separator") {
            if (program.options.table_mode || program.has_direct_table) {
                set_table_value(program.direct_table, "separator", require_string(args, i));
                program.has_direct_table = true;
            } else {
                set_object_value(program.direct_object, "separator", require_string(args, i));
                program.has_direct_object = true;
            }
        } else if (arg == "--prefix") {
            set_object_value(program.direct_object, "prefix", require_string(args, i));
            program.has_direct_object = true;
        } else if (arg == "--suffix") {
            set_object_value(program.direct_object, "suffix", require_string(args, i));
            program.has_direct_object = true;
        } else {
            throw std::runtime_error("Unknown option: " + arg);
        }
    }

    if (program.options.table_mode && program.has_direct_object) {
        throw std::runtime_error("Do not combine --table with object-fabric flags.");
    }

    return program;
}

std::string semantic_for(const TableSpec& spec, const std::string& pointer) {
    const auto found = spec.semantics.find(pointer);
    if (found != spec.semantics.end()) {
        return found->second;
    }
    return "identity_semantic(" + pointer + ")";
}

std::string make_cell_pointer(const TableSpec& spec,
                              std::uint64_t row_index,
                              std::uint64_t column_index,
                              const std::string& row_pointer,
                              const std::string& column_pointer) {
    std::ostringstream out;
    out << spec.cell_pointer_prefix
        << "::" << spec.table_name
        << "::r" << row_index
        << "::c" << column_index
        << "::" << row_pointer
        << "->" << column_pointer;
    return out.str();
}

std::string make_cell_identity_material(const TableSpec& spec,
                                        std::uint64_t cell_ordinal,
                                        std::uint64_t row_index,
                                        std::uint64_t column_index,
                                        const std::string& row_pointer,
                                        const std::string& column_pointer,
                                        const std::string& row_semantic,
                                        const std::string& column_semantic,
                                        const std::string& cell_pointer) {
    std::ostringstream out;
    out << "13.cpp\x1F"
        << spec.table_name << "\x1F"
        << cell_ordinal << "\x1F"
        << row_index << "\x1F"
        << column_index << "\x1F"
        << row_pointer << "\x1F"
        << column_pointer << "\x1F"
        << row_semantic << "\x1F"
        << column_semantic << "\x1F"
        << cell_pointer << "\x1F"
        << spec.boolean_engine << "\x1F"
        << spec.boolean_contract << "\x1F"
        << spec.barrier_policy << "\x1F"
        << spec.acceptance_state;
    return out.str();
}

void write_object_output(Writer& out,
                         const Options& options,
                         const ObjectSpec& spec,
                         std::uint64_t total,
                         std::uint64_t count) {
    out << "# cppdb-configure-source v1\n";
    out << "# source_kind=13.cpp/object_fabric_compatible_with_6(1).cpp\n";
    out << "# role=configured_object_fabric\n";
    out << "# record_mode=escaped_line\n";
    out << "# object_name=" << escape_field(spec.object_name) << '\n';
    out << "# input_name=" << escape_field(spec.input_name) << '\n';
    out << "# input_width=" << spec.input_width << '\n';
    out << "# input_size=" << spec.input_value.size() << '\n';
    out << "# flow_name=" << escape_field(spec.flow_name) << '\n';
    out << "# flow_type=" << flow_name(spec.flow) << '\n';
    out << "# output_name=" << escape_field(spec.output_name) << '\n';
    out << "# separator=" << escape_field(spec.separator) << '\n';
    out << "# prefix=" << escape_field(spec.prefix) << '\n';
    out << "# suffix=" << escape_field(spec.suffix) << '\n';
    out << "# expected_total=" << total << '\n';
    out << "# start=" << options.start << '\n';
    out << "# emitted_records=" << count << '\n';
    out << "# truncated=" << (options.start + count < total ? "true" : "false") << '\n';

    for (std::uint64_t i = 0; i < count; ++i) {
        const std::uint64_t ordinal = options.start + i;
        const std::string payload = make_payload(spec, ordinal);
        const std::string rendered = spec.prefix + payload + spec.suffix;

        out << "record\t"
            << ordinal << '\t'
            << escape_field(spec.object_name) << '\t'
            << escape_field(spec.input_name) << '\t'
            << escape_field(spec.flow_name) << '\t'
            << escape_field(spec.output_name) << '\t'
            << flow_name(spec.flow) << '\t'
            << payload.size() << '\t'
            << hex64(fnv1a_64(rendered)) << '\t'
            << escape_field(payload) << '\t'
            << escape_field(rendered) << '\n';
    }
}

void write_table_output(Writer& out,
                        const Options& options,
                        const TableSpec& spec,
                        std::uint64_t total,
                        std::uint64_t count) {
    const std::uint64_t row_count = static_cast<std::uint64_t>(spec.row_headings.size());
    const std::uint64_t column_count = static_cast<std::uint64_t>(spec.column_headings.size());

    out << "# book-sport-table-source v1\n";
    out << "# source_kind=13.cpp\n";
    out << "# role=formal_static_book_sport_table\n";
    out << "# purpose=general_purpose_engineering_architecture_and_static_accepted_information_implementation\n";
    out << "# record_mode=escaped_line\n";
    out << "# table_name=" << escape_field(spec.table_name) << '\n';
    out << "# output_name=" << escape_field(spec.output_name) << '\n';
    out << "# row_role=" << escape_field(spec.row_role) << '\n';
    out << "# column_role=" << escape_field(spec.column_role) << '\n';
    out << "# cell_role=" << escape_field(spec.cell_role) << '\n';
    out << "# boolean_engine=" << escape_field(spec.boolean_engine) << '\n';
    out << "# boolean_contract=" << escape_field(spec.boolean_contract) << '\n';
    out << "# barrier_policy=" << escape_field(spec.barrier_policy) << '\n';
    out << "# acceptance_state=" << escape_field(spec.acceptance_state) << '\n';
    out << "# hard_barrier=true\n";
    out << "# boolean_arithmetic_evaluation=deferred\n";
    out << "# row_count=" << row_count << '\n';
    out << "# column_count=" << column_count << '\n';
    out << "# expected_total=" << total << '\n';
    out << "# start=" << options.start << '\n';
    out << "# emitted_cells=" << count << '\n';
    out << "# truncated=" << (options.start + count < total ? "true" : "false") << '\n';
    out << "# schema.row=row index pointer pointer_hash semantic_hash role semantic\n";
    out << "# schema.column=column index pointer pointer_hash semantic_hash role semantic\n";
    out << "# schema.cell=cell ordinal row_index column_index row_pointer column_pointer cell_pointer row_semantic_hash column_semantic_hash cell_identity_hash acceptance_state barrier_policy boolean_engine boolean_contract row_semantic column_semantic\n";

    for (std::uint64_t r = 0; r < row_count; ++r) {
        const std::string& pointer = spec.row_headings[static_cast<std::size_t>(r)];
        const std::string semantic = semantic_for(spec, pointer);
        out << "row\t"
            << r << '\t'
            << escape_field(pointer) << '\t'
            << hex64(fnv1a_64(pointer)) << '\t'
            << hex64(fnv1a_64(semantic)) << '\t'
            << escape_field(spec.row_role) << '\t'
            << escape_field(semantic) << '\n';
    }

    for (std::uint64_t c = 0; c < column_count; ++c) {
        const std::string& pointer = spec.column_headings[static_cast<std::size_t>(c)];
        const std::string semantic = semantic_for(spec, pointer);
        out << "column\t"
            << c << '\t'
            << escape_field(pointer) << '\t'
            << hex64(fnv1a_64(pointer)) << '\t'
            << hex64(fnv1a_64(semantic)) << '\t'
            << escape_field(spec.column_role) << '\t'
            << escape_field(semantic) << '\n';
    }

    for (std::uint64_t i = 0; i < count; ++i) {
        const std::uint64_t cell_ordinal = options.start + i;
        const std::uint64_t row_index = cell_ordinal / column_count;
        const std::uint64_t column_index = cell_ordinal % column_count;

        const std::string& row_pointer = spec.row_headings[static_cast<std::size_t>(row_index)];
        const std::string& column_pointer = spec.column_headings[static_cast<std::size_t>(column_index)];
        const std::string row_semantic = semantic_for(spec, row_pointer);
        const std::string column_semantic = semantic_for(spec, column_pointer);
        const std::string cell_pointer = make_cell_pointer(spec, row_index, column_index,
                                                           row_pointer, column_pointer);
        const std::string identity_material = make_cell_identity_material(spec,
                                                                          cell_ordinal,
                                                                          row_index,
                                                                          column_index,
                                                                          row_pointer,
                                                                          column_pointer,
                                                                          row_semantic,
                                                                          column_semantic,
                                                                          cell_pointer);
        const std::string identity_hash = hex64(fnv1a_64(identity_material));

        out << "cell\t"
            << cell_ordinal << '\t'
            << row_index << '\t'
            << column_index << '\t'
            << escape_field(row_pointer) << '\t'
            << escape_field(column_pointer) << '\t'
            << escape_field(cell_pointer) << '\t'
            << hex64(fnv1a_64(row_semantic)) << '\t'
            << hex64(fnv1a_64(column_semantic)) << '\t'
            << identity_hash << '\t'
            << escape_field(spec.acceptance_state) << '\t'
            << escape_field(spec.barrier_policy) << '\t'
            << escape_field(spec.boolean_engine) << '\t'
            << escape_field(spec.boolean_contract) << '\t'
            << escape_field(row_semantic) << '\t'
            << escape_field(column_semantic) << '\n';
    }
}

void print_object_plan(const Options& options,
                       const ObjectSpec& spec,
                       std::uint64_t total,
                       std::uint64_t count) {
    std::cout
        << "13.cpp object-fabric dry run\n"
        << "  object: " << spec.object_name << '\n'
        << "  output: " << spec.output_target << '\n'
        << "  flow: " << flow_name(spec.flow) << '\n'
        << "  input width: " << spec.input_width << '\n'
        << "  expected total: " << total << '\n'
        << "  start: " << options.start << '\n'
        << "  records selected: " << count << '\n'
        << "  execute: false\n\n";
}

void print_table_plan(const Options& options,
                      const TableSpec& spec,
                      std::uint64_t total,
                      std::uint64_t count) {
    std::cout
        << "13.cpp Book Sport Table dry run\n"
        << "  table: " << spec.table_name << '\n'
        << "  output: " << spec.output_target << '\n'
        << "  rows: " << spec.row_headings.size() << '\n'
        << "  columns: " << spec.column_headings.size() << '\n'
        << "  expected cells: " << total << '\n'
        << "  start: " << options.start << '\n'
        << "  cells selected: " << count << '\n'
        << "  boolean engine: " << spec.boolean_engine << '\n'
        << "  barrier policy: " << spec.barrier_policy << '\n'
        << "  execute: false\n\n";
}

void emit_work_units(const Options& options, const std::vector<WorkUnit>& units) {
    std::map<std::string, bool> initialized_targets;

    for (const WorkUnit& unit : units) {
        if (unit.kind == WorkKind::book_sport_table) {
            const TableSpec& spec = unit.table;
            validate_spec(spec);
            const std::uint64_t total = expected_total(spec);
            const std::uint64_t count = requested_count(options, total);
            validate_safety(options, spec.table_name, count);

            if (!options.execute) {
                print_table_plan(options, spec, total, count);
                continue;
            }

            if (spec.output_target == "-" || equals_ignore_case(spec.output_target, "stdout")) {
                StreamSink sink(std::cout);
                Writer writer(sink);
                write_table_output(writer, options, spec, total, count);
                continue;
            }

            const bool already_initialized = initialized_targets[spec.output_target];
            if (!already_initialized && !options.overwrite && file_exists(spec.output_target)) {
                throw std::runtime_error("Output file already exists. Use --overwrite to replace it: " +
                                         spec.output_target);
            }

            FileSink sink(spec.output_target, already_initialized ? "ab" : "wb");
            Writer writer(sink);
            write_table_output(writer, options, spec, total, count);
            initialized_targets[spec.output_target] = true;
            std::cout << "Wrote " << count << " Book Sport table cells for "
                      << spec.table_name << " to " << spec.output_target << '\n';
        } else {
            const ObjectSpec& spec = unit.object;
            validate_spec(spec);
            const std::uint64_t total = expected_total(spec);
            const std::uint64_t count = requested_count(options, total);
            validate_safety(options, spec.object_name, count);

            if (!options.execute) {
                print_object_plan(options, spec, total, count);
                continue;
            }

            if (spec.output_target == "-" || equals_ignore_case(spec.output_target, "stdout")) {
                StreamSink sink(std::cout);
                Writer writer(sink);
                write_object_output(writer, options, spec, total, count);
                continue;
            }

            const bool already_initialized = initialized_targets[spec.output_target];
            if (!already_initialized && !options.overwrite && file_exists(spec.output_target)) {
                throw std::runtime_error("Output file already exists. Use --overwrite to replace it: " +
                                         spec.output_target);
            }

            FileSink sink(spec.output_target, already_initialized ? "ab" : "wb");
            Writer writer(sink);
            write_object_output(writer, options, spec, total, count);
            initialized_targets[spec.output_target] = true;
            std::cout << "Wrote " << count << " object-fabric records for "
                      << spec.object_name << " to " << spec.output_target << '\n';
        }
    }

    if (!options.execute) {
        std::cout << "Add --execute to write the escaped source-record output.\n";
    }
}

std::vector<WorkUnit> resolve_work_units(const Program& program, const char* executable) {
    if (!program.options.sample_config_path.empty()) {
        return {};
    }

    const bool uses_config = !program.options.config_path.empty();
    const bool uses_direct_object = program.has_direct_object;
    const bool uses_direct_table = program.has_direct_table;

    if ((uses_config ? 1 : 0) + (program.options.menu ? 1 : 0) +
        (uses_direct_object ? 1 : 0) + (uses_direct_table ? 1 : 0) > 1) {
        throw std::runtime_error("Use only one input mode: --config, --menu, direct object flags, or direct table flags.");
    }

    if (uses_config) {
        return load_config(program.options.config_path);
    }

    if (program.options.menu) {
        if (program.options.table_mode) {
            WorkUnit unit;
            unit.kind = WorkKind::book_sport_table;
            unit.table = prompt_table_spec();
            return {unit};
        }
        WorkUnit unit;
        unit.kind = WorkKind::object_fabric;
        unit.object = prompt_object_spec();
        return {unit};
    }

    if (uses_direct_table) {
        validate_spec(program.direct_table);
        WorkUnit unit;
        unit.kind = WorkKind::book_sport_table;
        unit.table = program.direct_table;
        return {unit};
    }

    if (uses_direct_object) {
        validate_spec(program.direct_object);
        WorkUnit unit;
        unit.kind = WorkKind::object_fabric;
        unit.object = program.direct_object;
        return {unit};
    }

    print_help(executable);
    return {};
}

int run(int argc, char** argv) {
    Program program = parse_program(argc, argv);

    if (!program.options.sample_config_path.empty()) {
        write_sample_config(program.options.sample_config_path, program.options.overwrite);
        std::cout << "Wrote sample config to " << program.options.sample_config_path << '\n';
        return 0;
    }

    const std::vector<WorkUnit> units = resolve_work_units(program, argv[0]);
    if (units.empty()) {
        return 0;
    }

    emit_work_units(program.options, units);
    return 0;
}

} // namespace

int main(int argc, char** argv) {
    try {
        return run(argc, argv);
    } catch (const std::exception& ex) {
        std::cerr << "13.cpp error: " << ex.what() << '\n';
        return 1;
    }
}
