(() => {
    'use strict';

    const state = {
        database: {
            events: [],
            map: { dimensions: { rows: 1, columns: 1 }, cells: [[null]] },
        },
        activeMode: 'tab',
        toastTimer: null,
    };

    const elements = {};

    document.addEventListener('DOMContentLoaded', init);

    function init() {
        bindElements();
        bindEvents();
        updateSymbolCounts();
        state.canvas = new InfiniteMemoryMap(elements.canvas, elements.canvasShell, openNode);
        loadDatabase();
    }

    function bindElements() {
        const ids = [
            'database-state', 'database-state-text', 'event-form', 'alphabet', 'alphabet-count',
            'string-input', 'input-count', 'event-label', 'proof-strip', 'capture-button',
            'empty-node', 'latest-node', 'node-count', 'latest-label', 'latest-sequential-id',
            'latest-event-id', 'latest-timestamp', 'latest-symbols', 'latest-number-class',
            'copy-id', 'map-dimensions', 'event-grid', 'grid-empty', 'search-input',
            'search-count', 'search-results', 'canvas-width', 'canvas-height', 'apply-context',
            'fit-map', 'center-map', 'zoom-readout', 'canvas-shell', 'memory-canvas',
            'node-dialog', 'dialog-close', 'dialog-label', 'dialog-value', 'dialog-meta', 'toast',
        ];

        for (const id of ids) {
            const key = id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
            elements[key] = document.getElementById(id);
        }

        elements.canvas = elements.memoryCanvas;
        elements.modeTabs = [...document.querySelectorAll('.mode-tab')];
        elements.modePanels = [...document.querySelectorAll('.mode-panel')];
    }

    function bindEvents() {
        elements.alphabet.addEventListener('input', updateSymbolCounts);
        elements.stringInput.addEventListener('input', updateSymbolCounts);
        elements.eventForm.addEventListener('submit', createEvent);
        elements.copyId.addEventListener('click', copyLatestId);
        elements.searchInput.addEventListener('input', renderSearch);
        elements.dialogClose.addEventListener('click', () => elements.nodeDialog.close());
        elements.nodeDialog.addEventListener('click', (event) => {
            if (event.target === elements.nodeDialog) {
                elements.nodeDialog.close();
            }
        });

        for (const tab of elements.modeTabs) {
            tab.addEventListener('click', () => switchMode(tab.dataset.mode));
        }

        elements.applyContext.addEventListener('click', applyContextWindow);
        elements.fitMap.addEventListener('click', () => state.canvas.fitMap());
        elements.centerMap.addEventListener('click', () => state.canvas.center());
    }

    async function loadDatabase() {
        setConnection('loading', 'Connecting');
        try {
            const response = await fetch('api.php', { headers: { Accept: 'application/json' } });
            const payload = await readResponse(response);
            state.database = payload.database;
            renderAll();
            setConnection('online', `${state.database.events.length} nodes online`);
        } catch (error) {
            setConnection('error', 'Database unavailable');
            showToast(error.message, true);
        }
    }

    async function createEvent(event) {
        event.preventDefault();
        const alphabet = elements.alphabet.value;
        const input = elements.stringInput.value;
        const label = elements.eventLabel.value;

        if (!alphabet || [...alphabet].length < 2) {
            showProof('failed', 'Alphabet rejected.', 'Define at least two unique Unicode symbols.');
            elements.alphabet.focus();
            return;
        }

        elements.captureButton.disabled = true;
        elements.captureButton.firstElementChild.textContent = 'Verifying exact reverse…';
        showProof('', 'Computing sequential-string ID…', 'The server is ranking and reversing the string.');

        try {
            const response = await fetch('api.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ action: 'create-event', alphabet, input, label }),
            });
            const payload = await readResponse(response);
            state.database = payload.database;
            renderAll(payload.node);
            showProof(
                'verified',
                'Exact reverse verified.',
                `ID ${formatId(payload.node['sequential-string ID'], 34)} decoded to the original string.`,
            );
            setConnection('online', `${state.database.events.length} nodes online`);
            showToast('Memory event verified and committed to the JSON map.');
        } catch (error) {
            showProof('failed', 'Capture stopped.', error.message);
            showToast(error.message, true);
        } finally {
            elements.captureButton.disabled = false;
            elements.captureButton.firstElementChild.textContent = 'Compile + capture node';
        }
    }

    async function readResponse(response) {
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new Error(`Server returned an unreadable response (${response.status}).`);
        }

        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || `Request failed (${response.status}).`);
        }

        return payload;
    }

    function renderAll(preferredLatest = null) {
        const events = state.database.events || [];
        const dimensions = state.database.map?.dimensions || { rows: 1, columns: 1 };
        const latest = preferredLatest || events.at(-1) || null;

        elements.nodeCount.textContent = `${events.length} ${events.length === 1 ? 'node' : 'nodes'}`;
        elements.mapDimensions.textContent = `${dimensions.columns} × ${dimensions.rows}`;
        renderLatest(latest);
        renderGrid();
        renderSearch();
        state.canvas.setDatabase(state.database);
    }

    function renderLatest(node) {
        elements.emptyNode.hidden = Boolean(node);
        elements.latestNode.hidden = !node;
        if (!node) return;

        elements.latestLabel.textContent = node.label;
        elements.latestSequentialId.textContent = node['sequential-string ID'];
        elements.latestEventId.textContent = node.ID;
        elements.latestTimestamp.textContent = formatTimestamp(node['time-stamp']);
        elements.latestSymbols.textContent = node.metrics?.['value-symbols'] ?? [...node.value].length;
        elements.latestNumberClass.textContent = node.metrics?.['native-integer'] ? 'small integer' : 'BigInt decimal';
    }

    function renderGrid() {
        const events = state.database.events || [];
        const eventById = new Map(events.map((event) => [event.ID, event]));
        const cells = state.database.map?.cells || [[null]];
        const side = state.database.map?.dimensions?.columns || 1;

        elements.eventGrid.replaceChildren();
        elements.eventGrid.style.gridTemplateColumns = `repeat(${side}, minmax(150px, 1fr))`;
        elements.eventGrid.style.minWidth = side > 7 ? `${side * 162}px` : '0';
        elements.gridEmpty.hidden = events.length !== 0;
        elements.eventGrid.hidden = events.length === 0;

        if (events.length === 0) return;

        cells.forEach((row, rowIndex) => {
            row.forEach((id, columnIndex) => {
                const node = id ? eventById.get(id) : null;
                if (!node) {
                    const emptyCell = document.createElement('div');
                    emptyCell.className = 'event-cell empty';
                    emptyCell.innerHTML = `<span class="cell-coordinate"><span>[${rowIndex}, ${columnIndex}]</span><span>vacant</span></span>`;
                    elements.eventGrid.append(emptyCell);
                    return;
                }

                const cell = document.createElement('button');
                cell.type = 'button';
                cell.className = 'event-cell';
                cell.dataset.nodeId = node.ID;

                const coordinate = document.createElement('span');
                coordinate.className = 'cell-coordinate';
                coordinate.innerHTML = `<span>[${rowIndex}, ${columnIndex}]</span><span class="cell-node-dot" aria-hidden="true"></span>`;
                const label = document.createElement('strong');
                label.textContent = node.label;
                const idCode = document.createElement('code');
                idCode.textContent = node['sequential-string ID'];
                cell.append(coordinate, label, idCode);
                cell.addEventListener('click', () => openNode(node));
                elements.eventGrid.append(cell);
            });
        });
    }

    function renderSearch() {
        const query = elements.searchInput.value.trim().toLocaleLowerCase();
        const events = state.database.events || [];
        const results = events.filter((node) => {
            if (!query) return true;
            return [node.label, node.value, node.ID, node['sequential-string ID'], node['time-stamp']]
                .some((value) => String(value).toLocaleLowerCase().includes(query));
        });

        elements.searchCount.textContent = `${results.length} ${results.length === 1 ? 'result' : 'results'}`;
        elements.searchResults.replaceChildren();

        if (results.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'panel-empty';
            empty.textContent = query ? 'No memory nodes match this search.' : 'No memory nodes to search.';
            elements.searchResults.append(empty);
            return;
        }

        for (const node of results.slice().reverse()) {
            const result = document.createElement('button');
            result.type = 'button';
            result.className = 'search-result';
            const label = document.createElement('strong');
            label.textContent = node.label;
            const value = document.createElement('span');
            value.textContent = visibleValue(node.value);
            const id = document.createElement('code');
            id.textContent = node['sequential-string ID'];
            result.append(label, value, id);
            result.addEventListener('click', () => openNode(node));
            elements.searchResults.append(result);
        }
    }

    function switchMode(mode) {
        state.activeMode = mode;
        for (const tab of elements.modeTabs) {
            const active = tab.dataset.mode === mode;
            tab.classList.toggle('active', active);
            tab.setAttribute('aria-selected', String(active));
        }
        for (const panel of elements.modePanels) {
            const active = panel.id === `${mode}-mode`;
            panel.classList.toggle('active', active);
            panel.hidden = !active;
        }

        if (mode === 'search') {
            elements.searchInput.focus();
        }
        if (mode === 'picture') {
            requestAnimationFrame(() => {
                state.canvas.resize();
                state.canvas.fitMap();
            });
        }
    }

    function openNode(node) {
        elements.dialogLabel.textContent = node.label;
        elements.dialogValue.textContent = node.value || '(empty string)';
        elements.dialogMeta.replaceChildren();

        const fields = [
            ['Sequential-string ID', node['sequential-string ID']],
            ['Backward-computed value', node['backward-computed value'] ?? '(legacy event)'],
            ['Exact reverse proof', node['backward-computation']?.['matches-value'] ? 'valid / true' : 'not recorded'],
            ['Event ID', node.ID],
            ['Time stamp', node['time-stamp']],
            ['Alphabet symbols', node.metrics?.['alphabet-symbols'] ?? [...node.alphabet].length],
            ['Value symbols', node.metrics?.['value-symbols'] ?? [...node.value].length],
        ];
        for (const [term, description] of fields) {
            const row = document.createElement('div');
            const dt = document.createElement('dt');
            const dd = document.createElement('dd');
            dt.textContent = term;
            dd.textContent = description;
            row.append(dt, dd);
            elements.dialogMeta.append(row);
        }

        elements.nodeDialog.showModal();
    }

    function applyContextWindow() {
        const width = clamp(Number(elements.canvasWidth.value), 320, 2400);
        const height = clamp(Number(elements.canvasHeight.value), 240, 1400);
        elements.canvasWidth.value = width;
        elements.canvasHeight.value = height;
        elements.canvasShell.style.width = `${width}px`;
        elements.canvasShell.style.height = `${height}px`;
        state.canvas.resize();
        showToast(`Context window set to ${width} × ${height} CSS pixels.`);
    }

    async function copyLatestId() {
        const value = elements.latestSequentialId.textContent;
        if (!value) return;
        try {
            await navigator.clipboard.writeText(value);
            showToast('Sequential-string ID copied.');
        } catch {
            showToast('Clipboard access was not available.', true);
        }
    }

    function updateSymbolCounts() {
        const alphabetLength = [...elements.alphabet.value].length;
        const inputLength = [...elements.stringInput.value].length;
        elements.alphabetCount.textContent = `${alphabetLength} ${alphabetLength === 1 ? 'symbol' : 'symbols'}`;
        elements.inputCount.textContent = `${inputLength} ${inputLength === 1 ? 'symbol' : 'symbols'}`;
    }

    function showProof(status, title, detail) {
        elements.proofStrip.classList.remove('verified', 'failed');
        if (status) elements.proofStrip.classList.add(status);
        elements.proofStrip.querySelector('strong').textContent = title;
        elements.proofStrip.querySelector('small').textContent = detail;
        elements.proofStrip.querySelector('.proof-icon').textContent = status === 'verified' ? '✓' : status === 'failed' ? '!' : '↺';
    }

    function setConnection(status, message) {
        elements.databaseState.classList.remove('online', 'error');
        if (status === 'online' || status === 'error') elements.databaseState.classList.add(status);
        elements.databaseStateText.textContent = message;
    }

    function showToast(message, isError = false) {
        clearTimeout(state.toastTimer);
        elements.toast.textContent = message;
        elements.toast.classList.toggle('error', isError);
        elements.toast.classList.add('show');
        state.toastTimer = setTimeout(() => elements.toast.classList.remove('show'), 3600);
    }

    function visibleValue(value) {
        if (value === '') return '(empty string)';
        return value.replace(/\n/g, ' ↵ ').replace(/\t/g, ' ⇥ ');
    }

    function formatId(id, maxLength) {
        return id.length <= maxLength ? id : `${id.slice(0, maxLength - 7)}…${id.slice(-6)}`;
    }

    function formatTimestamp(value) {
        const date = new Date(value);
        return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
    }

    function clamp(value, minimum, maximum) {
        return Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));
    }

    class InfiniteMemoryMap {
        constructor(canvas, shell, onNodeClick) {
            this.canvas = canvas;
            this.shell = shell;
            this.context = canvas.getContext('2d');
            this.onNodeClick = onNodeClick;
            this.database = { events: [], map: { dimensions: { columns: 1 } } };
            this.nodes = [];
            this.zoom = 1;
            this.panX = 0;
            this.panY = 0;
            this.dragging = false;
            this.dragDistance = 0;
            this.pointerStart = null;
            this.cellStep = 190;
            this.nodeWidth = 148;
            this.nodeHeight = 106;
            this.hasPosition = false;

            this.canvas.addEventListener('pointerdown', (event) => this.pointerDown(event));
            this.canvas.addEventListener('pointermove', (event) => this.pointerMove(event));
            this.canvas.addEventListener('pointerup', (event) => this.pointerUp(event));
            this.canvas.addEventListener('pointercancel', (event) => this.pointerUp(event));
            this.canvas.addEventListener('wheel', (event) => this.wheel(event), { passive: false });
            window.addEventListener('resize', () => this.resize());
            this.resize();
        }

        setDatabase(database) {
            this.database = database;
            const events = database.events || [];
            const eventById = new Map(events.map((event) => [event.ID, event]));
            const cells = database.map?.cells || [[null]];
            const side = database.map?.dimensions?.columns || 1;
            const centerOffset = (side - 1) / 2;
            this.nodes = [];

            cells.forEach((row, rowIndex) => {
                row.forEach((id, columnIndex) => {
                    const node = id ? eventById.get(id) : null;
                    if (node) {
                        this.nodes.push({
                            node,
                            row: rowIndex,
                            column: columnIndex,
                            x: (columnIndex - centerOffset) * this.cellStep,
                            y: (rowIndex - centerOffset) * this.cellStep,
                        });
                    }
                });
            });

            if (!this.hasPosition) {
                this.fitMap();
                this.hasPosition = true;
            } else {
                this.draw();
            }
        }

        resize() {
            const rectangle = this.shell.getBoundingClientRect();
            const width = Math.max(1, Math.round(rectangle.width));
            const height = Math.max(1, Math.round(rectangle.height));
            const ratio = Math.min(window.devicePixelRatio || 1, 2);
            this.width = width;
            this.height = height;
            this.ratio = ratio;
            this.canvas.width = Math.round(width * ratio);
            this.canvas.height = Math.round(height * ratio);
            this.canvas.style.width = `${width}px`;
            this.canvas.style.height = `${height}px`;
            this.draw();
        }

        center() {
            this.panX = this.width / 2;
            this.panY = this.height / 2;
            this.draw();
        }

        fitMap() {
            const side = this.database.map?.dimensions?.columns || 1;
            const boundsWidth = Math.max(this.nodeWidth, ((side - 1) * this.cellStep) + this.nodeWidth);
            const boundsHeight = Math.max(this.nodeHeight, ((side - 1) * this.cellStep) + this.nodeHeight);
            const availableWidth = Math.max(100, (this.width || 1100) - 100);
            const availableHeight = Math.max(100, (this.height || 620) - 100);
            this.zoom = clamp(Math.min(availableWidth / boundsWidth, availableHeight / boundsHeight, 1.4), 0.16, 2.5);
            this.center();
        }

        pointerDown(event) {
            this.dragging = true;
            this.dragDistance = 0;
            this.pointerStart = { x: event.clientX, y: event.clientY, panX: this.panX, panY: this.panY };
            this.canvas.setPointerCapture(event.pointerId);
            this.canvas.classList.add('dragging');
        }

        pointerMove(event) {
            if (!this.dragging || !this.pointerStart) return;
            const deltaX = event.clientX - this.pointerStart.x;
            const deltaY = event.clientY - this.pointerStart.y;
            this.dragDistance = Math.max(this.dragDistance, Math.hypot(deltaX, deltaY));
            this.panX = this.pointerStart.panX + deltaX;
            this.panY = this.pointerStart.panY + deltaY;
            this.draw();
        }

        pointerUp(event) {
            if (!this.dragging) return;
            this.dragging = false;
            this.canvas.classList.remove('dragging');
            if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);

            if (this.dragDistance < 5) {
                const rectangle = this.canvas.getBoundingClientRect();
                const world = this.toWorld(event.clientX - rectangle.left, event.clientY - rectangle.top);
                const hit = this.nodes.find((item) => (
                    Math.abs(world.x - item.x) <= this.nodeWidth / 2
                    && Math.abs(world.y - item.y) <= this.nodeHeight / 2
                ));
                if (hit) this.onNodeClick(hit.node);
            }
        }

        wheel(event) {
            event.preventDefault();
            const rectangle = this.canvas.getBoundingClientRect();
            const mouseX = event.clientX - rectangle.left;
            const mouseY = event.clientY - rectangle.top;
            const worldBefore = this.toWorld(mouseX, mouseY);
            const factor = Math.exp(-event.deltaY * 0.0012);
            this.zoom = clamp(this.zoom * factor, 0.12, 4);
            this.panX = mouseX - (worldBefore.x * this.zoom);
            this.panY = mouseY - (worldBefore.y * this.zoom);
            this.draw();
        }

        toWorld(screenX, screenY) {
            return {
                x: (screenX - this.panX) / this.zoom,
                y: (screenY - this.panY) / this.zoom,
            };
        }

        draw() {
            if (!this.context || !this.width || !this.height) return;
            const context = this.context;
            context.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
            context.clearRect(0, 0, this.width, this.height);
            context.fillStyle = '#070a0f';
            context.fillRect(0, 0, this.width, this.height);
            this.drawInfiniteGrid(context);

            context.save();
            context.translate(this.panX, this.panY);
            context.scale(this.zoom, this.zoom);
            this.drawAxes(context);
            for (const item of this.nodes) this.drawNode(context, item);
            context.restore();

            elements.zoomReadout.textContent = `${Math.round(this.zoom * 100)}%`;
        }

        drawInfiniteGrid(context) {
            const spacing = Math.max(16, 44 * this.zoom);
            const offsetX = ((this.panX % spacing) + spacing) % spacing;
            const offsetY = ((this.panY % spacing) + spacing) % spacing;
            context.beginPath();
            for (let x = offsetX; x <= this.width; x += spacing) {
                context.moveTo(x, 0);
                context.lineTo(x, this.height);
            }
            for (let y = offsetY; y <= this.height; y += spacing) {
                context.moveTo(0, y);
                context.lineTo(this.width, y);
            }
            context.strokeStyle = 'rgba(72, 91, 115, 0.13)';
            context.lineWidth = 1;
            context.stroke();
        }

        drawAxes(context) {
            const left = -this.panX / this.zoom;
            const top = -this.panY / this.zoom;
            const right = left + (this.width / this.zoom);
            const bottom = top + (this.height / this.zoom);
            context.beginPath();
            context.moveTo(left, 0);
            context.lineTo(right, 0);
            context.moveTo(0, top);
            context.lineTo(0, bottom);
            context.strokeStyle = 'rgba(53, 217, 231, 0.20)';
            context.lineWidth = 1 / this.zoom;
            context.stroke();
        }

        drawNode(context, item) {
            const { node, x, y, row, column } = item;
            const left = x - (this.nodeWidth / 2);
            const top = y - (this.nodeHeight / 2);
            const radius = 9;

            context.beginPath();
            context.roundRect(left, top, this.nodeWidth, this.nodeHeight, radius);
            context.fillStyle = 'rgba(15, 22, 32, 0.96)';
            context.fill();
            context.strokeStyle = 'rgba(53, 217, 231, 0.58)';
            context.lineWidth = 1.2 / this.zoom;
            context.stroke();

            context.fillStyle = '#35d9e7';
            context.fillRect(left + 13, top + 14, 7, 7);
            context.fillStyle = '#667186';
            context.font = `8px ${getComputedStyle(document.documentElement).getPropertyValue('--mono')}`;
            context.textBaseline = 'top';
            context.fillText(`[${row}, ${column}]`, left + 27, top + 13);

            context.fillStyle = '#f4f7fb';
            context.font = `600 11px ${getComputedStyle(document.documentElement).getPropertyValue('--sans')}`;
            context.fillText(this.truncate(node.label, 19), left + 13, top + 39);

            context.fillStyle = '#60e7a8';
            context.font = `8px ${getComputedStyle(document.documentElement).getPropertyValue('--mono')}`;
            context.fillText(this.truncate(node['sequential-string ID'], 25), left + 13, top + 64);

            context.fillStyle = '#596275';
            context.fillText(this.truncate(node.ID, 25), left + 13, top + 82);
        }

        truncate(value, length) {
            const text = String(value);
            return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
        }
    }
})();
