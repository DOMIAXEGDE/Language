<?php

declare(strict_types=1);

header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');

$defaultAlphabet = implode('', array_map(static fn (int $code): string => chr($code), range(32, 126)));
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="dark">
    <title>Memory Square · Sequential String Database</title>
    <link rel="stylesheet" href="assets/app.css">
</head>
<body>
    <header class="site-header">
        <div class="matrix-field" aria-hidden="true"></div>
        <a class="brand" href="#top" aria-label="Memory Square home">
            <span class="brand-mark">M<sup>2</sup></span>
            <span>
                <strong>Memory Square</strong>
                <small>reversible sequential-string database</small>
            </span>
        </a>
        <div class="header-actions">
            <form class="export-report-form" action="api.php" method="get">
                <input type="hidden" name="action" value="export-report">
                <button
                    class="export-report-button"
                    id="export-report"
                    type="submit"
                    aria-label="Download complete database and event report as report.pdf"
                    title="Download a complete report of events.json"
                >
                    <span class="export-report-label">Export report.pdf</span>
                    <span class="export-report-icon" aria-hidden="true">↓</span>
                </button>
            </form>
            <div class="database-state" id="database-state">
                <span class="state-light" aria-hidden="true"></span>
                <span id="database-state-text">Connecting</span>
            </div>
        </div>
    </header>

    <main id="top">
        <section class="hero" aria-labelledby="hero-title">
            <div>
                <p class="eyebrow">PHP 8.5 / JSON event memory</p>
                <h1 id="hero-title">Give every valid string<br>a place in sequence.</h1>
                <p class="hero-copy">Define the alphabet, capture a string, prove the exact reverse, then place its event node in a living square map.</p>
            </div>
            <div class="process-rail" aria-label="System process">
                <div><span>00</span><strong>Alphabet</strong></div>
                <div><span>01</span><strong>String</strong></div>
                <div><span>02</span><strong>Verify</strong></div>
                <div><span>03</span><strong>Remember</strong></div>
                <div><span>04</span><strong>Map</strong></div>
            </div>
        </section>

        <section class="workbench" aria-label="Memory event compiler">
            <form class="compiler-panel" id="event-form" novalidate>
                <div class="panel-heading">
                    <div>
                        <p class="step-label">INPUT / PROCESS</p>
                        <h2>Compile a memory event</h2>
                    </div>
                    <span class="mode-badge">SHORTLEX</span>
                </div>

                <label class="field-group">
                    <span class="field-topline">
                        <span><b>00</b> Input alphabet</span>
                        <output id="alphabet-count">95 symbols</output>
                    </span>
                    <textarea id="alphabet" name="alphabet" rows="3" spellcheck="false" required><?= htmlspecialchars($defaultAlphabet, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></textarea>
                    <small>Each Unicode code point is one symbol. Order determines rank; duplicates are rejected.</small>
                </label>

                <label class="field-group">
                    <span class="field-topline">
                        <span><b>01</b> String-input</span>
                        <output id="input-count">0 symbols</output>
                    </span>
                    <textarea id="string-input" name="input" rows="5" spellcheck="false" placeholder="Enter a string composed from the alphabet…" required></textarea>
                </label>

                <label class="field-group compact-field">
                    <span class="field-topline"><span><b>03</b> Event label</span></span>
                    <input id="event-label" name="label" type="text" maxlength="120" placeholder="A useful name for this memory">
                </label>

                <div class="proof-strip" id="proof-strip" aria-live="polite">
                    <span class="proof-icon">↺</span>
                    <span><strong>Round-trip proof runs on capture.</strong><small>The ID is only returned when decode(encode(input)) is exact.</small></span>
                </div>

                <button class="primary-action" id="capture-button" type="submit">
                    <span>Compile + capture node</span>
                    <span aria-hidden="true">→</span>
                </button>
            </form>

            <aside class="output-panel" aria-labelledby="latest-title">
                <div class="panel-heading">
                    <div>
                        <p class="step-label">OUTPUT</p>
                        <h2 id="latest-title">Latest node</h2>
                    </div>
                    <span class="node-count" id="node-count">0 nodes</span>
                </div>

                <div class="empty-node" id="empty-node">
                    <span>∅</span>
                    <p>No memory events yet.</p>
                    <small>Your first verified node will appear here.</small>
                </div>

                <article class="latest-node" id="latest-node" hidden>
                    <div class="node-orbit" aria-hidden="true"><span></span></div>
                    <p class="latest-label" id="latest-label"></p>
                    <div class="id-block">
                        <span>Sequential-string ID</span>
                        <code id="latest-sequential-id"></code>
                    </div>
                    <dl class="node-meta">
                        <div><dt>Event ID</dt><dd id="latest-event-id"></dd></div>
                        <div><dt>Time stamp</dt><dd id="latest-timestamp"></dd></div>
                        <div><dt>Value symbols</dt><dd id="latest-symbols"></dd></div>
                        <div><dt>Number class</dt><dd id="latest-number-class"></dd></div>
                    </dl>
                    <button type="button" class="copy-button" id="copy-id">Copy sequential ID</button>
                </article>
            </aside>
        </section>

        <section class="map-section" aria-labelledby="map-title">
            <div class="map-heading">
                <div>
                    <p class="step-label">04 / MEMORY-EVENT-NODE MAP</p>
                    <h2 id="map-title">The square array</h2>
                </div>
                <div class="map-dimensions" id="map-dimensions">1 × 1</div>
            </div>

            <nav class="mode-tabs" aria-label="Map modes" role="tablist">
                <button type="button" class="mode-tab active" data-mode="tab" role="tab" aria-selected="true">Tab mode</button>
                <button type="button" class="mode-tab" data-mode="search" role="tab" aria-selected="false">Search mode</button>
                <button type="button" class="mode-tab" data-mode="picture" role="tab" aria-selected="false">Infinite picture</button>
            </nav>

            <div class="mode-panel active" id="tab-mode" role="tabpanel">
                <div class="event-grid" id="event-grid"></div>
                <div class="panel-empty" id="grid-empty">Capture an event to populate the square array.</div>
            </div>

            <div class="mode-panel" id="search-mode" role="tabpanel" hidden>
                <div class="search-toolbar">
                    <label>
                        <span class="sr-only">Search events</span>
                        <input type="search" id="search-input" placeholder="Search label, value, event ID, or sequential ID…" autocomplete="off">
                    </label>
                    <span id="search-count">0 results</span>
                </div>
                <div class="search-results" id="search-results"></div>
            </div>

            <div class="mode-panel" id="picture-mode" role="tabpanel" hidden>
                <div class="picture-toolbar">
                    <div class="context-controls">
                        <label>Width <input id="canvas-width" type="number" min="320" max="2400" step="10" value="1100"> px</label>
                        <label>Height <input id="canvas-height" type="number" min="240" max="1400" step="10" value="620"> px</label>
                        <button type="button" id="apply-context">Apply context</button>
                    </div>
                    <div class="canvas-actions">
                        <span id="zoom-readout">100%</span>
                        <button type="button" id="fit-map">Fit map</button>
                        <button type="button" id="center-map">Center</button>
                    </div>
                </div>
                <div class="canvas-shell" id="canvas-shell">
                    <canvas id="memory-canvas" width="1100" height="620" aria-label="Pannable and zoomable infinite memory map"></canvas>
                    <div class="canvas-hint">Drag to pan · wheel to zoom · click a node to inspect</div>
                </div>
            </div>
        </section>
    </main>

    <dialog id="node-dialog">
        <button type="button" class="dialog-close" id="dialog-close" aria-label="Close">×</button>
        <p class="step-label">MEMORY EVENT NODE</p>
        <h2 id="dialog-label"></h2>
        <pre id="dialog-value"></pre>
        <dl class="dialog-meta" id="dialog-meta"></dl>
    </dialog>

    <div class="toast" id="toast" role="status" aria-live="polite"></div>

    <script src="assets/app.js" defer></script>
</body>
</html>
