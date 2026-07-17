<?php

declare(strict_types=1);

namespace MemoryMap;

use JsonException;

/**
 * Builds a dependency-free, printable PDF snapshot of the JSON event database.
 *
 * The PDF uses the standard Helvetica and Courier fonts so the application stays
 * portable. Non-ASCII characters are emitted as explicit U+XXXX code points,
 * preserving every value even when a PDF reader lacks a matching Unicode font.
 */
final class DatabaseReportPdf
{
    private const PAGE_WIDTH = 595.28;
    private const PAGE_HEIGHT = 841.89;
    private const MARGIN_LEFT = 46.0;
    private const MARGIN_RIGHT = 46.0;
    private const BODY_TOP = 82.0;
    private const BODY_BOTTOM = 790.0;

    /** @var list<array{section: string, commands: list<string>}> */
    private array $pages = [];
    private int $pageIndex = -1;
    private float $cursor = self::BODY_TOP;
    private string $currentSection = 'DATABASE REPORT';

    /** @param array<string, mixed> $database */
    public function __construct(
        private readonly array $database,
        private readonly string $sourceFile = 'events.json',
        private readonly ?string $generatedAt = null,
    ) {
    }

    public function render(): string
    {
        $this->pages = [];
        $this->pageIndex = -1;
        $this->buildReport();

        return $this->compilePdf();
    }

    private function buildReport(): void
    {
        $events = isset($this->database['events']) && is_array($this->database['events'])
            ? array_values($this->database['events'])
            : [];
        $map = isset($this->database['map']) && is_array($this->database['map'])
            ? $this->database['map']
            : [];
        $dimensions = isset($map['dimensions']) && is_array($map['dimensions'])
            ? $map['dimensions']
            : [];
        $rows = max(1, (int) ($dimensions['rows'] ?? 1));
        $columns = max(1, (int) ($dimensions['columns'] ?? 1));
        $cellCount = $rows * $columns;
        $eventCount = count($events);
        $generatedAt = $this->generatedAt ?? EventStore::timestamp();

        $this->addPage('DATABASE REPORT');
        $this->drawRect(0, 0, self::PAGE_WIDTH, 276, [0.035, 0.055, 0.090]);
        $this->drawRect(self::MARGIN_LEFT, 102, 54, 4, [0.208, 0.851, 0.906]);
        $this->writeAt(self::MARGIN_LEFT, 132, 'MEMORY SQUARE', 'F2', 11, [0.208, 0.851, 0.906]);
        $this->writeAt(self::MARGIN_LEFT, 171, 'Database and', 'F2', 35, [0.96, 0.98, 1.0]);
        $this->writeAt(self::MARGIN_LEFT, 211, 'event report', 'F2', 35, [0.96, 0.98, 1.0]);
        $this->writeAt(
            self::MARGIN_LEFT,
            247,
            sprintf('Complete snapshot of %s - generated %s', $this->sourceFile, $generatedAt),
            'F1',
            9,
            [0.65, 0.71, 0.80],
        );

        $this->cursor = 320;
        $summaryWidth = (self::PAGE_WIDTH - self::MARGIN_LEFT - self::MARGIN_RIGHT - 18) / 2;
        $this->summaryCard(self::MARGIN_LEFT, $this->cursor, $summaryWidth, 'EVENTS', (string) $eventCount, 'verified memory nodes');
        $this->summaryCard(self::MARGIN_LEFT + $summaryWidth + 18, $this->cursor, $summaryWidth, 'MAP', sprintf('%d x %d', $columns, $rows), sprintf('%d cells / %d vacant', $cellCount, max(0, $cellCount - $eventCount)));
        $this->cursor += 108;

        $this->sectionHeading('Snapshot scope');
        $this->paragraph(
            'This report contains every top-level database property, every memory-map coordinate, and every field stored on every event. Values are never shortened. Non-ASCII symbols are represented as explicit U+ code points so the source data remains unambiguous in every PDF reader.',
            10,
        );
        $this->cursor += 8;
        $this->field('Source file', $this->sourceFile);
        $this->field('Schema', $this->scalarValue($this->database['schema'] ?? null));
        $this->field('Database updated at', $this->scalarValue($this->database['updated-at'] ?? null));
        $this->field('Report generated at', $generatedAt);

        $this->addPage('DATABASE DETAILS');
        $this->pageTitle('Database details', 'Top-level fields and complete square-map placement');

        $topLevel = $this->database;
        unset($topLevel['events'], $topLevel['map']);
        $this->sectionHeading('Top-level properties');
        foreach ($this->flatten($topLevel) as [$path, $value]) {
            $this->field($path, $value);
        }

        $this->cursor += 8;
        $this->sectionHeading('Map summary');
        $this->field('map.dimensions.rows', (string) $rows);
        $this->field('map.dimensions.columns', (string) $columns);
        $this->field('map.cells.total', (string) $cellCount);
        $this->field('map.cells.occupied', (string) $eventCount);
        $this->field('map.cells.vacant', (string) max(0, $cellCount - $eventCount));

        $this->cursor += 8;
        $this->sectionHeading('Map cells');
        $cells = isset($map['cells']) && is_array($map['cells']) ? $map['cells'] : [];
        for ($row = 0; $row < $rows; $row++) {
            for ($column = 0; $column < $columns; $column++) {
                $value = isset($cells[$row]) && is_array($cells[$row]) && array_key_exists($column, $cells[$row])
                    ? $cells[$row][$column]
                    : null;
                $this->field(sprintf('map.cells[%d][%d]', $row, $column), $this->scalarValue($value), true);
            }
        }

        if ($events === []) {
            $this->addPage('EVENTS');
            $this->pageTitle('Event details', 'No events are stored in this database snapshot');
            $this->paragraph('The events array is empty. The database and its vacant map are fully represented in the preceding pages.', 10);
            return;
        }

        foreach ($events as $index => $event) {
            $number = $index + 1;
            $this->addPage(sprintf('EVENT %d / %d', $number, $eventCount));
            $label = is_array($event) ? $this->scalarValue($event['label'] ?? 'Untitled memory') : 'Unsupported event value';
            $this->pageTitle($label, sprintf('Complete event record %d of %d', $number, $eventCount));

            if (!is_array($event)) {
                $this->field(sprintf('events[%d]', $index), $this->scalarValue($event));
                continue;
            }

            foreach ($this->flatten($event) as [$path, $value]) {
                $this->field($path, $value, $path === 'value');
            }
        }
    }

    private function pageTitle(string $title, string $subtitle): void
    {
        $this->writeAt(self::MARGIN_LEFT, $this->cursor, $title, 'F2', 22, [0.06, 0.09, 0.14]);
        $this->cursor += 27;
        $this->writeAt(self::MARGIN_LEFT, $this->cursor, $subtitle, 'F1', 9, [0.39, 0.45, 0.55]);
        $this->cursor += 28;
        $this->drawLine(self::MARGIN_LEFT, $this->cursor, self::PAGE_WIDTH - self::MARGIN_RIGHT, $this->cursor, [0.82, 0.85, 0.89], 0.7);
        $this->cursor += 24;
    }

    private function sectionHeading(string $title): void
    {
        $this->ensureSpace(35);
        $this->writeAt(self::MARGIN_LEFT, $this->cursor, strtoupper($title), 'F2', 9, [0.10, 0.55, 0.61]);
        $this->cursor += 22;
    }

    private function summaryCard(float $x, float $top, float $width, string $label, string $value, string $detail): void
    {
        $this->drawRect($x, $top, $width, 82, [0.965, 0.975, 0.988], [0.82, 0.86, 0.90]);
        $this->writeAt($x + 16, $top + 22, $label, 'F2', 8, [0.10, 0.55, 0.61]);
        $this->writeAt($x + 16, $top + 49, $value, 'F2', 22, [0.06, 0.09, 0.14]);
        $this->writeAt($x + 16, $top + 68, $detail, 'F1', 8, [0.39, 0.45, 0.55]);
    }

    private function paragraph(string $value, float $size = 9): void
    {
        $lines = $this->wrap($this->asciiSafe($value), self::PAGE_WIDTH - self::MARGIN_LEFT - self::MARGIN_RIGHT, $size, false);
        $lineHeight = $size * 1.48;
        foreach ($lines as $line) {
            $this->ensureSpace($lineHeight);
            $this->writeAt(self::MARGIN_LEFT, $this->cursor, $line, 'F1', $size, [0.20, 0.24, 0.31]);
            $this->cursor += $lineHeight;
        }
    }

    private function field(string $label, string $value, bool $emphasize = false): void
    {
        $safeLabel = $this->asciiSafe($label);
        $safeValue = $this->asciiSafe($value);
        $lineHeight = 11.2;
        $valueLines = $this->wrap($safeValue, self::PAGE_WIDTH - self::MARGIN_LEFT - self::MARGIN_RIGHT, 8.4, true);
        $this->ensureSpace(17 + min(1, count($valueLines)) * $lineHeight);

        $this->writeAt(self::MARGIN_LEFT, $this->cursor, strtoupper($safeLabel), 'F2', 7.3, [0.39, 0.45, 0.55]);
        $this->cursor += 13;
        foreach ($valueLines as $line) {
            $this->ensureSpace($lineHeight);
            if ($this->cursor === self::BODY_TOP) {
                $this->writeAt(self::MARGIN_LEFT, $this->cursor, strtoupper($safeLabel) . ' - CONTINUED', 'F2', 7.3, [0.39, 0.45, 0.55]);
                $this->cursor += 13;
            }
            $this->writeAt(
                self::MARGIN_LEFT,
                $this->cursor,
                $line === '' ? '(empty string)' : $line,
                'F3',
                8.4,
                $emphasize ? [0.06, 0.25, 0.29] : [0.10, 0.13, 0.18],
            );
            $this->cursor += $lineHeight;
        }
        $this->cursor += 7;
    }

    private function ensureSpace(float $height, ?string $continuationSection = null): void
    {
        if ($this->cursor + $height <= self::BODY_BOTTOM) {
            return;
        }

        $section = $continuationSection ?? $this->currentSection;
        $section = preg_replace('/(?:\s+(?:-|\()\s*CONTINUED\)?)+$/i', '', $section) ?? $section;
        $this->addPage($section . ' - CONTINUED');
    }

    private function addPage(string $section): void
    {
        $this->pages[] = ['section' => $section, 'commands' => []];
        $this->pageIndex = count($this->pages) - 1;
        $this->currentSection = $section;
        $this->cursor = self::BODY_TOP;
        $this->drawRect(0, 0, self::PAGE_WIDTH, self::PAGE_HEIGHT, [1.0, 1.0, 1.0]);
    }

    private function writeAt(float $x, float $top, string $text, string $font, float $size, array $color): void
    {
        $safe = $this->escapePdfString($this->asciiSafe($text));
        $y = self::PAGE_HEIGHT - $top;
        $this->command(sprintf(
            'BT /%s %.2F Tf %.3F %.3F %.3F rg 1 0 0 1 %.2F %.2F Tm (%s) Tj ET',
            $font,
            $size,
            $color[0],
            $color[1],
            $color[2],
            $x,
            $y,
            $safe,
        ));
    }

    private function drawRect(float $x, float $top, float $width, float $height, array $fill, ?array $stroke = null): void
    {
        $y = self::PAGE_HEIGHT - $top - $height;
        $operation = $stroke === null ? 'f' : 'B';
        $command = sprintf('q %.3F %.3F %.3F rg ', $fill[0], $fill[1], $fill[2]);
        if ($stroke !== null) {
            $command .= sprintf('%.3F %.3F %.3F RG 0.6 w ', $stroke[0], $stroke[1], $stroke[2]);
        }
        $command .= sprintf('%.2F %.2F %.2F %.2F re %s Q', $x, $y, $width, $height, $operation);
        $this->command($command);
    }

    private function drawLine(float $x1, float $top1, float $x2, float $top2, array $color, float $width): void
    {
        $this->command(sprintf(
            'q %.3F %.3F %.3F RG %.2F w %.2F %.2F m %.2F %.2F l S Q',
            $color[0],
            $color[1],
            $color[2],
            $width,
            $x1,
            self::PAGE_HEIGHT - $top1,
            $x2,
            self::PAGE_HEIGHT - $top2,
        ));
    }

    private function command(string $command): void
    {
        $this->pages[$this->pageIndex]['commands'][] = $command;
    }

    /** @return list<array{0: string, 1: string}> */
    private function flatten(mixed $value, string $prefix = ''): array
    {
        if (!is_array($value)) {
            return [[$prefix === '' ? 'value' : $prefix, $this->scalarValue($value)]];
        }

        if ($value === []) {
            return [[$prefix === '' ? 'value' : $prefix, '[]']];
        }

        $result = [];
        foreach ($value as $key => $child) {
            $path = $prefix === ''
                ? (string) $key
                : (is_int($key) ? sprintf('%s[%d]', $prefix, $key) : sprintf('%s.%s', $prefix, $key));
            foreach ($this->flatten($child, $path) as $field) {
                $result[] = $field;
            }
        }

        return $result;
    }

    private function scalarValue(mixed $value): string
    {
        if ($value === null) {
            return 'null';
        }
        if ($value === true) {
            return 'true';
        }
        if ($value === false) {
            return 'false';
        }
        if (is_string($value)) {
            return $value;
        }
        if (is_int($value) || is_float($value)) {
            return (string) $value;
        }

        try {
            return json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        } catch (JsonException) {
            return '[unserializable value]';
        }
    }

    /** @return list<string> */
    private function wrap(string $value, float $availableWidth, float $fontSize, bool $monospace): array
    {
        if ($value === '') {
            return [''];
        }

        $characterWidth = $fontSize * ($monospace ? 0.60 : 0.51);
        $limit = max(1, (int) floor($availableWidth / $characterWidth));
        $logicalLines = explode("\n", $value);
        $lines = [];

        foreach ($logicalLines as $logicalLine) {
            if ($logicalLine === '') {
                $lines[] = '';
                continue;
            }

            $remaining = $logicalLine;
            while (strlen($remaining) > $limit) {
                $candidate = substr($remaining, 0, $limit + 1);
                $break = strrpos($candidate, ' ');
                if ($break === false || $break < (int) ($limit * 0.45)) {
                    $break = $limit;
                }
                $lines[] = rtrim(substr($remaining, 0, $break));
                $remaining = ltrim(substr($remaining, $break));
            }
            $lines[] = $remaining;
        }

        return $lines;
    }

    private function asciiSafe(string $value): string
    {
        if ($value === '') {
            return '';
        }

        $characters = preg_split('//u', $value, -1, PREG_SPLIT_NO_EMPTY);
        if ($characters === false) {
            return '[invalid UTF-8] ' . strtoupper(bin2hex($value));
        }

        $result = '';
        foreach ($characters as $character) {
            $codePoint = mb_ord($character, 'UTF-8');
            if ($codePoint === 10) {
                $result .= '\\n';
            } elseif ($codePoint === 13) {
                $result .= '\\r';
            } elseif ($codePoint === 9) {
                $result .= '\\t';
            } elseif ($codePoint >= 32 && $codePoint <= 126) {
                $result .= $character;
            } elseif ($codePoint < 32 || $codePoint === 127) {
                $result .= sprintf('<U+%04X>', $codePoint);
            } else {
                $result .= sprintf('<U+%04X>', $codePoint);
            }
        }

        return $result;
    }

    private function escapePdfString(string $value): string
    {
        return str_replace(['\\', '(', ')'], ['\\\\', '\\(', '\\)'], $value);
    }

    private function compilePdf(): string
    {
        $pageCount = count($this->pages);
        $objects = [];
        $objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
        $objects[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
        $objects[4] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
        $objects[5] = '<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>';

        $pageObjectIds = [];
        $nextObjectId = 6;
        foreach ($this->pages as $index => $page) {
            $pageNumber = $index + 1;
            $commands = $page['commands'];
            $commands[] = sprintf(
                'BT /F2 7.5 Tf 0.39 0.45 0.55 rg 1 0 0 1 %.2F %.2F Tm (%s) Tj ET',
                self::MARGIN_LEFT,
                self::PAGE_HEIGHT - 34,
                $this->escapePdfString($this->asciiSafe($page['section'])),
            );
            $commands[] = sprintf(
                'BT /F1 7.5 Tf 0.39 0.45 0.55 rg 1 0 0 1 %.2F %.2F Tm (MEMORY SQUARE / %s) Tj ET',
                self::PAGE_WIDTH - self::MARGIN_RIGHT - 103,
                self::PAGE_HEIGHT - 34,
                $this->escapePdfString($this->asciiSafe($this->sourceFile)),
            );
            $commands[] = sprintf(
                'q 0.82 0.85 0.89 RG 0.6 w %.2F %.2F m %.2F %.2F l S Q',
                self::MARGIN_LEFT,
                37.5,
                self::PAGE_WIDTH - self::MARGIN_RIGHT,
                37.5,
            );
            $commands[] = sprintf(
                'BT /F1 7.5 Tf 0.39 0.45 0.55 rg 1 0 0 1 %.2F 22 Tm (Complete database snapshot) Tj ET',
                self::MARGIN_LEFT,
            );
            $commands[] = sprintf(
                'BT /F2 7.5 Tf 0.10 0.55 0.61 rg 1 0 0 1 %.2F 22 Tm (PAGE %d OF %d) Tj ET',
                self::PAGE_WIDTH - self::MARGIN_RIGHT - 70,
                $pageNumber,
                $pageCount,
            );

            $content = implode("\n", $commands) . "\n";
            $contentObjectId = $nextObjectId++;
            $pageObjectId = $nextObjectId++;
            $objects[$contentObjectId] = sprintf("<< /Length %d >>\nstream\n%sendstream", strlen($content), $content);
            $objects[$pageObjectId] = sprintf(
                '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2F %.2F] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents %d 0 R >>',
                self::PAGE_WIDTH,
                self::PAGE_HEIGHT,
                $contentObjectId,
            );
            $pageObjectIds[] = $pageObjectId;
        }

        $objects[2] = sprintf(
            '<< /Type /Pages /Count %d /Kids [%s] >>',
            $pageCount,
            implode(' ', array_map(static fn (int $id): string => $id . ' 0 R', $pageObjectIds)),
        );
        $infoObjectId = $nextObjectId;
        $objects[$infoObjectId] = sprintf(
            '<< /Title (%s) /Author (Memory Square) /Subject (Complete events.json database and event report) /Creator (Memory Square PHP exporter) >>',
            $this->escapePdfString('Memory Square database and event report'),
        );

        ksort($objects);
        $pdf = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n";
        $offsets = [0 => 0];
        foreach ($objects as $id => $object) {
            $offsets[$id] = strlen($pdf);
            $pdf .= sprintf("%d 0 obj\n%s\nendobj\n", $id, $object);
        }

        $xrefOffset = strlen($pdf);
        $objectCount = max(array_keys($objects));
        $pdf .= sprintf("xref\n0 %d\n", $objectCount + 1);
        $pdf .= "0000000000 65535 f \n";
        for ($id = 1; $id <= $objectCount; $id++) {
            $pdf .= sprintf("%010d 00000 n \n", $offsets[$id]);
        }
        $pdf .= sprintf(
            "trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n",
            $objectCount + 1,
            $infoObjectId,
            $xrefOffset,
        );

        return $pdf;
    }
}
