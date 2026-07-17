<?php

declare(strict_types=1);

use MemoryMap\EventStore;
use MemoryMap\DatabaseReportPdf;
use MemoryMap\SequentialStringId;

require_once __DIR__ . '/src/bootstrap.php';

header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

$store = new EventStore(__DIR__ . '/data/events.json');

try {
    if ($_SERVER['REQUEST_METHOD'] === 'GET') {
        if (($_GET['action'] ?? null) === 'export-report') {
            sendPdfReport($store);
        }

        respond([
            'ok' => true,
            'database' => $store->read(),
            'limits' => [
                'maxStringSymbols' => SequentialStringId::MAX_STRING_SYMBOLS,
                'maxAlphabetSymbols' => SequentialStringId::MAX_ALPHABET_SYMBOLS,
            ],
        ]);
    }

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        header('Allow: GET, POST');
        respond(['ok' => false, 'error' => 'Method not allowed.'], 405);
    }

    $payload = readPayload();
    if (($payload['action'] ?? '') !== 'create-event') {
        respond(['ok' => false, 'error' => 'Unknown action.'], 400);
    }

    $alphabet = requireString($payload, 'alphabet');
    $input = requireString($payload, 'input');
    $label = trim(requireString($payload, 'label'));
    if ($label === '') {
        $label = 'Untitled memory';
    }
    if (mb_strlen($label) > 120) {
        throw new InvalidArgumentException('The label must be 120 symbols or fewer.');
    }

    $sequence = new SequentialStringId($alphabet);
    $sequentialId = $sequence->encodeVerified($input);
    $backwardValue = $sequence->decode($sequentialId);

    $node = [
        'time-stamp' => EventStore::timestamp(),
        'label' => $label,
        'value' => $input,
        'ID' => createEventId(),
        'sequential-string ID' => $sequentialId,
        'backward-computed value' => $backwardValue,
        'backward-computation' => [
            'algorithm' => 'shortlex-unrank/1.0',
            'matches-value' => hash_equals($input, $backwardValue),
        ],
        'alphabet' => $alphabet,
        'metrics' => [
            'alphabet-symbols' => $sequence->alphabetSize(),
            'value-symbols' => mb_strlen($input),
            'sequential-ID-digits' => strlen($sequentialId),
            'native-integer' => isNativeInteger($sequentialId),
        ],
    ];

    $database = $store->append($node);
    respond(['ok' => true, 'node' => $node, 'database' => $database], 201);
} catch (InvalidArgumentException $exception) {
    respond(['ok' => false, 'error' => $exception->getMessage()], 422);
} catch (Throwable $exception) {
    error_log((string) $exception);
    respond(['ok' => false, 'error' => 'The memory event could not be processed.'], 500);
}

/** @return array<string, mixed> */
function readPayload(): array
{
    $contentType = strtolower((string) ($_SERVER['CONTENT_TYPE'] ?? ''));
    if (!str_starts_with($contentType, 'application/json')) {
        throw new InvalidArgumentException('Send the request as application/json.');
    }

    $body = file_get_contents('php://input');
    if ($body === false || trim($body) === '') {
        throw new InvalidArgumentException('The request body is empty.');
    }

    try {
        $payload = json_decode($body, true, 32, JSON_THROW_ON_ERROR);
    } catch (JsonException $exception) {
        throw new InvalidArgumentException('The request body is not valid JSON.', 0, $exception);
    }

    if (!is_array($payload)) {
        throw new InvalidArgumentException('The request body must be a JSON object.');
    }

    return $payload;
}

/** @param array<string, mixed> $payload */
function requireString(array $payload, string $field): string
{
    if (!array_key_exists($field, $payload) || !is_string($payload[$field])) {
        throw new InvalidArgumentException(sprintf('Field “%s” must be a string.', $field));
    }

    return $payload[$field];
}

function createEventId(): string
{
    $milliseconds = (int) floor(microtime(true) * 1000);

    return sprintf('mem_%s_%s', base_convert((string) $milliseconds, 10, 36), bin2hex(random_bytes(5)));
}

function isNativeInteger(string $decimal): bool
{
    $max = (string) PHP_INT_MAX;

    return strlen($decimal) < strlen($max)
        || (strlen($decimal) === strlen($max) && strcmp($decimal, $max) <= 0);
}

function sendPdfReport(EventStore $store): never
{
    $pdf = (new DatabaseReportPdf(
        $store->read(),
        'events.json',
        EventStore::timestamp(),
    ))->render();

    header('Content-Type: application/pdf');
    header('Content-Disposition: attachment; filename="report.pdf"');
    header('Content-Length: ' . strlen($pdf));
    echo $pdf;
    exit;
}

/** @param array<string, mixed> $payload */
function respond(array $payload, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(
        $payload,
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
    );
    exit;
}
