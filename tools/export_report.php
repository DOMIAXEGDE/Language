<?php

declare(strict_types=1);

use MemoryMap\DatabaseReportPdf;
use MemoryMap\EventStore;

require_once dirname(__DIR__) . '/src/bootstrap.php';

$root = dirname(__DIR__);
$databasePath = $argv[1] ?? ($root . '/data/events.json');
$outputPath = $argv[2] ?? ($root . '/output/pdf/report.pdf');
$directory = dirname($outputPath);
if (!is_dir($directory) && !mkdir($directory, 0775, true) && !is_dir($directory)) {
    throw new RuntimeException(sprintf('Unable to create %s.', $directory));
}

$database = (new EventStore($databasePath))->read();
$pdf = (new DatabaseReportPdf($database, basename($databasePath), EventStore::timestamp()))->render();
if (file_put_contents($outputPath, $pdf, LOCK_EX) === false) {
    throw new RuntimeException(sprintf('Unable to write %s.', $outputPath));
}

fwrite(STDOUT, sprintf(
    "Wrote %s (%d bytes, %d events, %d map cells).\n",
    $outputPath,
    strlen($pdf),
    count($database['events']),
    $database['map']['cells-total'],
));

