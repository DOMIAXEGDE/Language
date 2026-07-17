<?php

declare(strict_types=1);

use MemoryMap\EventStore;
use MemoryMap\SequentialStringId;

require_once dirname(__DIR__) . '/src/bootstrap.php';

$root = dirname(__DIR__);
$databasePath = $argv[1] ?? ($root . '/data/events.json');
$compiledPath = $argv[2] ?? ($root . '/build/artifacts/compiler-events.json');

$database = readJsonObject($databasePath);
$compiled = readJsonObject($compiledPath);

if (!isset($database['events']) || !is_array($database['events'])) {
    throw new RuntimeException('The existing database has no events array.');
}
if (!isset($compiled['events']) || !is_array($compiled['events'])) {
    throw new RuntimeException('The compiler output has no events array.');
}

// Preserve the original seed records and any user-created PHP records, but make
// compiler documentation replacement idempotent across repeated artifact builds.
$events = array_values(array_filter(
    $database['events'],
    static fn (mixed $event): bool => is_array($event)
        && !str_starts_with((string) ($event['ID'] ?? ''), 'gpil_'),
));
$seedCount = count($events);

foreach ($events as $index => &$event) {
    $event = normalizeAndProveEvent($event, sprintf('existing event %d', $index + 1));
}
unset($event);

foreach ($compiled['events'] as $index => $event) {
    if (!is_array($event)) {
        throw new RuntimeException(sprintf('Compiled event %d is not an object.', $index + 1));
    }
    $events[] = normalizeAndProveEvent($event, sprintf('compiled event %d', $index + 1));
}

$ids = [];
foreach ($events as $event) {
    $id = (string) $event['ID'];
    if (isset($ids[$id])) {
        throw new RuntimeException(sprintf('Duplicate event ID %s.', $id));
    }
    $ids[$id] = true;
}

$updatedAt = EventStore::timestamp();
$map = EventStore::buildSquareMap($events);
$state = [
    'schema' => 'memory-event-node/2.0',
    'updated-at' => $updatedAt,
    'database-details' => [
        'schema' => 'memory-event-node/2.0',
        'updated-at' => $updatedAt,
        'map-dimensions-rows' => $map['dimensions']['rows'],
        'map-dimensions-columns' => $map['dimensions']['columns'],
        'map-cells-total' => $map['cells-total'],
        'map-cells-occupied' => $map['cells-occupied'],
        'map-cells-vacant' => $map['cells-vacant'],
    ],
    'compiler' => $compiled['compiler'] ?? [],
    'instruction-set' => $compiled['instruction-set'] ?? [],
    'sequential-ID-mathematics' => [
        'alphabet' => 'A=(a_0,...,a_(b-1)); ordered, unique, 2 <= b <= 1024',
        'empty-value' => 'ID(empty)=0',
        'shorter-buckets' => 'S_n=sum(k=1..n-1,b^k)',
        'within-bucket-rank' => 'R(x)=sum(i=0..n-1,d_i*b^(n-1-i))',
        'forward' => 'ID(x)=1+S_n+R(x)',
        'backward-steps' => [
            'normalize the non-negative decimal ID; zero decodes to empty',
            'subtract successive b^length buckets until the containing length is found',
            'subtract one to obtain the zero-based within-bucket offset',
            'perform repeated divmod by b from the last symbol position to the first',
            'map each remainder to its ordered alphabet symbol and concatenate',
            'require the reconstructed UTF-8 byte string to equal the original value',
        ],
        'proof' => 'Disjoint length buckets and fixed-width base-b notation are bijective, so rank and un-rank are mutual inverses.',
    ],
    'system-manifest' => buildSystemManifest($root),
    'event-counts' => [
        'preserved-events' => $seedCount,
        'instruction-and-component-events' => count($compiled['events']),
        'events-total' => count($events),
    ],
    'events' => $events,
    'map' => $map,
];

$encoded = json_encode(
    $state,
    JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
) . PHP_EOL;

if (file_put_contents($databasePath, $encoded, LOCK_EX) === false) {
    throw new RuntimeException(sprintf('Unable to write %s.', $databasePath));
}

fwrite(STDOUT, sprintf(
    "Rebuilt %s with %d preserved + %d compiled = %d proven events; map %d x %d (%d vacant).\n",
    $databasePath,
    $seedCount,
    count($compiled['events']),
    count($events),
    $map['dimensions']['columns'],
    $map['dimensions']['rows'],
    $map['cells-vacant'],
));

/** @return array<string, mixed> */
function readJsonObject(string $path): array
{
    $contents = file_get_contents($path);
    if ($contents === false) {
        throw new RuntimeException(sprintf('Unable to read %s.', $path));
    }
    $value = json_decode($contents, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($value)) {
        throw new RuntimeException(sprintf('%s is not a JSON object.', $path));
    }
    return $value;
}

/**
 * @param array<string, mixed> $event
 * @return array<string, mixed>
 */
function normalizeAndProveEvent(array $event, string $context): array
{
    foreach (['time-stamp', 'label', 'value', 'ID', 'sequential-string ID', 'alphabet'] as $field) {
        if (!array_key_exists($field, $event) || !is_string($event[$field])) {
            throw new RuntimeException(sprintf('%s field %s must be a string.', $context, $field));
        }
    }

    $sequence = new SequentialStringId($event['alphabet']);
    $computedId = $sequence->encodeVerified($event['value']);
    if (!hash_equals($computedId, $event['sequential-string ID'])) {
        throw new RuntimeException(sprintf('%s has a sequential ID inconsistent with its value.', $context));
    }
    $backward = $sequence->decode($event['sequential-string ID']);
    if (!hash_equals($event['value'], $backward)) {
        throw new RuntimeException(sprintf('%s failed exact backward computation.', $context));
    }

    $event['backward-computed value'] = $backward;
    $event['backward-computation'] = [
        'algorithm' => 'shortlex-unrank/1.0',
        'matches-value' => true,
    ];
    $event['metrics'] = [
        'alphabet-symbols' => $sequence->alphabetSize(),
        'value-symbols' => mb_strlen($event['value']),
        'sequential-ID-digits' => strlen($event['sequential-string ID']),
        'native-integer' => isNativeDecimal($event['sequential-string ID']),
    ];
    if (!isset($event['instruction']) || !is_array($event['instruction'])) {
        $event['instruction'] = [
            'language' => 'Memory Square seed/1.0',
            'source-line' => null,
            'operation' => 'knowledge_literal',
            'source' => 'preserved from the original 100-event constructive-mathematics database',
        ];
    }
    return $event;
}

function isNativeDecimal(string $decimal): bool
{
    $maximum = (string) PHP_INT_MAX;
    return strlen($decimal) < strlen($maximum)
        || (strlen($decimal) === strlen($maximum) && strcmp($decimal, $maximum) <= 0);
}

/** @return array<string, mixed> */
function buildSystemManifest(string $root): array
{
    $components = [
        ['README.md', 'Markdown', 'operator entry point, build, run, test, and artifact instructions'],
        ['prompt.md', 'Markdown', 'original five-stage PHP system requirements'],
        ['index.php', 'PHP/HTML', 'secured web entry point and event/map interface'],
        ['api.php', 'PHP', 'strict GET/POST API, event proof construction, storage, and PDF response'],
        ['src/bootstrap.php', 'PHP', 'dependency loader'],
        ['src/BigNatural.php', 'PHP', 'dependency-free arbitrary-precision natural arithmetic'],
        ['src/SequentialStringId.php', 'PHP', 'UTF-8 shortlex rank, un-rank, and exact proof'],
        ['src/EventStore.php', 'PHP', 'locked JSON persistence and derived square map'],
        ['src/DatabaseReportPdf.php', 'PHP', 'complete paginated PDF serializer'],
        ['assets/app.js', 'JavaScript', 'API client, event views, search, and interactive infinite map'],
        ['assets/app.css', 'CSS', 'responsive visual system and printable interface styling'],
        ['template/compiler.html', 'HTML/JavaScript', 'character-map and encode/decode guidance patterns'],
        ['compiler/CMakeLists.txt', 'CMake', 'C++20 compiler build and test definition'],
        ['compiler/src/main.cpp', 'C++20', 'GPIL lexer, parser, evaluator, arithmetic, proof, JSON, map, and CLI'],
        ['bin/gpilc.exe', 'Windows PE executable', 'self-contained compiled GPIL command-line compiler'],
        ['docs/GPIL.md', 'Markdown', 'language grammar, mathematics, semantics, schema, and pipeline specification'],
        ['examples/demo.gpil', 'GPIL', 'executable language demonstration'],
        ['examples/system_manifest.gpil', 'GPIL', 'one-line-per-event complete component documentation source'],
        ['tests/run.php', 'PHP', 'PHP arithmetic, rank, storage, map, and PDF regression tests'],
        ['tools/rebuild_database.php', 'PHP', 'cross-runtime proof validation, manifest merge, and database rebuild'],
        ['tools/export_report.php', 'PHP', 'stable report.pdf artifact generator'],
    ];

    $files = [];
    foreach ($components as [$relativePath, $language, $responsibility]) {
        $path = $root . '/' . $relativePath;
        if (!is_file($path)) {
            throw new RuntimeException(sprintf('Manifest component %s is missing.', $relativePath));
        }
        $files[] = [
            'path' => $relativePath,
            'language' => $language,
            'responsibility' => $responsibility,
            'bytes' => filesize($path),
            'sha256' => hash_file('sha256', $path),
        ];
    }

    return [
        'component-count' => count($files),
        'components' => $files,
        'GPIL-built-ins' => [
            'add', 'apply_directional_polarity', 'containerize', 'decontainerize',
            'transform_container', 'subtract', 'multiply', 'divide', 'modulo',
            'literal', 'identity', 'concat', 'symbol_length', 'reverse', 'replace',
            'equal', 'not', 'and', 'or', 'select', 'assert_equal', 'semantic_triple',
            'sequential_encode', 'sequential_decode', 'sequential_verify', 'map_coordinate',
        ],
        'C++-standard-library-components' => [
            'algorithm', 'chrono', 'cmath', 'cstdint', 'ctime', 'fstream', 'iomanip',
            'iostream', 'limits', 'optional', 'sstream', 'stdexcept', 'string',
            'string_view', 'utility', 'vector',
        ],
        'browser-built-ins-used' => [
            'fetch', 'JSON.stringify', 'navigator.clipboard.writeText', 'requestAnimationFrame',
            'setTimeout', 'clearTimeout', 'Map', 'Date', 'Math', 'document.createElement',
            'HTMLDialogElement.showModal', 'CanvasRenderingContext2D', 'PointerEvent', 'WheelEvent',
        ],
        'PHP-native-functions-by-component' => [
            'BigNatural.php' => ['preg_match', 'ltrim', 'strlen', 'strcmp', 'strrev', 'max', 'intdiv'],
            'SequentialStringId.php' => ['preg_match', 'mb_str_split', 'count', 'array_key_exists', 'sprintf', 'implode', 'array_fill'],
            'EventStore.php' => ['dirname', 'is_dir', 'mkdir', 'is_file', 'fopen', 'flock', 'stream_get_contents', 'rewind', 'ftruncate', 'fwrite', 'fflush', 'fclose', 'json_decode', 'json_encode', 'ceil', 'sqrt', 'intdiv', 'array_fill', 'file_put_contents'],
            'DatabaseReportPdf.php' => ['array_values', 'count', 'sprintf', 'strtoupper', 'explode', 'substr', 'strlen', 'preg_split', 'mb_ord', 'str_replace', 'ksort', 'json_encode'],
            'api.php' => ['header', 'str_starts_with', 'trim', 'mb_strlen', 'file_get_contents', 'json_decode', 'microtime', 'floor', 'base_convert', 'random_bytes', 'bin2hex', 'strlen', 'strcmp', 'hash_equals', 'http_response_code', 'error_log'],
            'index.php' => ['header', 'implode', 'array_map', 'range', 'chr', 'htmlspecialchars'],
        ],
    ];
}
