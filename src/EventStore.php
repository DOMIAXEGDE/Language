<?php

declare(strict_types=1);

namespace MemoryMap;

use DateTimeImmutable;
use DateTimeZone;
use RuntimeException;

final class EventStore
{
    public function __construct(private readonly string $path)
    {
        $directory = dirname($path);
        if (!is_dir($directory) && !mkdir($directory, 0775, true) && !is_dir($directory)) {
            throw new RuntimeException('Unable to create the JSON database directory.');
        }

        if (!is_file($this->path)) {
            $this->writeInitialState();
        }
    }

    /** @return array<string, mixed> */
    public function read(): array
    {
        $handle = fopen($this->path, 'rb');
        if ($handle === false) {
            throw new RuntimeException('Unable to open the JSON database.');
        }

        try {
            if (!flock($handle, LOCK_SH)) {
                throw new RuntimeException('Unable to lock the JSON database for reading.');
            }
            $contents = stream_get_contents($handle);
            flock($handle, LOCK_UN);
        } finally {
            fclose($handle);
        }

        return $this->decodeState($contents === false ? '' : $contents);
    }

    /**
     * @param array<string, mixed> $node
     * @return array<string, mixed>
     */
    public function append(array $node): array
    {
        $handle = fopen($this->path, 'c+b');
        if ($handle === false) {
            throw new RuntimeException('Unable to open the JSON database.');
        }

        try {
            if (!flock($handle, LOCK_EX)) {
                throw new RuntimeException('Unable to lock the JSON database for writing.');
            }

            rewind($handle);
            $contents = stream_get_contents($handle);
            $state = $this->decodeState($contents === false ? '' : $contents);
            $state['events'][] = $node;
            $state['updated-at'] = self::timestamp();
            $state['map'] = self::buildSquareMap($state['events']);

            $encoded = json_encode(
                $state,
                JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
            ) . PHP_EOL;

            rewind($handle);
            if (!ftruncate($handle, 0) || fwrite($handle, $encoded) === false || !fflush($handle)) {
                throw new RuntimeException('Unable to commit the JSON database update.');
            }
            flock($handle, LOCK_UN);
        } finally {
            fclose($handle);
        }

        return $state;
    }

    /** @param list<array<string, mixed>> $events */
    public static function buildSquareMap(array $events): array
    {
        $count = count($events);
        $side = max(1, (int) ceil(sqrt(max(1, $count))));
        $cells = array_fill(0, $side, array_fill(0, $side, null));

        foreach ($events as $index => $event) {
            $row = intdiv($index, $side);
            $column = $index % $side;
            $cells[$row][$column] = $event['ID'];
        }

        return [
            'dimensions' => ['rows' => $side, 'columns' => $side],
            'cells-total' => $side * $side,
            'cells-occupied' => $count,
            'cells-vacant' => ($side * $side) - $count,
            'cells' => $cells,
        ];
    }

    public static function timestamp(): string
    {
        return (new DateTimeImmutable('now', new DateTimeZone('UTC')))
            ->format('Y-m-d\TH:i:s.v\Z');
    }

    /** @return array<string, mixed> */
    private function decodeState(string $contents): array
    {
        if (trim($contents) === '') {
            return self::initialState();
        }

        try {
            $state = json_decode($contents, true, 512, JSON_THROW_ON_ERROR);
        } catch (\JsonException $exception) {
            throw new RuntimeException('The JSON database is not valid.', 0, $exception);
        }

        if (!is_array($state) || !isset($state['events']) || !is_array($state['events'])) {
            throw new RuntimeException('The JSON database has an unsupported structure.');
        }

        $state['map'] = self::buildSquareMap($state['events']);

        return $state;
    }

    private function writeInitialState(): void
    {
        $encoded = json_encode(
            self::initialState(),
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
        ) . PHP_EOL;

        if (file_put_contents($this->path, $encoded, LOCK_EX) === false) {
            throw new RuntimeException('Unable to initialize the JSON database.');
        }
    }

    /** @return array<string, mixed> */
    private static function initialState(): array
    {
        return [
            'schema' => 'memory-event-node/2.0',
            'updated-at' => self::timestamp(),
            'events' => [],
            'map' => self::buildSquareMap([]),
        ];
    }
}
