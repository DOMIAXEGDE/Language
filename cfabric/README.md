# cfabric

`cfabric` generates deterministic two-dimensional graphical worlds as JSON,
validates their geometry, renders them, and composes multiple generated worlds
without introducing collisions.

## Files

- `cfabric.c` — C11 procedural generator.
- `cfabric.exe` — tested GNU/Linux x86-64 build of `cfabric.c`.
- `cfabric.py` — independent validator and SVG/PNG renderer.
- `clyaers.py` — seedless world layer/composition utility. The filename keeps
  the requested spelling.
- `cfabric.example.conf` — example generator configuration.
- `Makefile` — build, demo, and validation targets.

## Structural interpretation

The supplied vocabulary is represented directly:

- An **object** is either a point or a straight line joining two points.
- A **canvas** is a closed boundary with at least three points, three lines, and
  six objects total. Generated canvases are separated axis-aligned rectangles.
- A **canvas-partition** is exactly two boundary points plus one straight line
  spanning its owner canvas.
- Coordinates are signed integers, which are exact rational values and
  therefore stay inside the specified zero/negative-rational/positive-rational
  number domain.

Required structural incidence is not treated as a collision: adjacent boundary
segments may share their declared endpoint, and a partition may share its two
declared endpoints with its owner canvas. Every other point contact, point on a
line, line crossing, line overlap, canvas touch, or canvas overlap is rejected.
Partition endpoints split the canvas boundary, so the data contains no hidden
T-junctions.

The count fields are canonical rational forms with denominator 1:
`a/b=x`, `c/d=y`, and `e/f=z`. JSON also stores `x xor y xor z` as
`xor_signature` and preserves the supplied final expression as text. It is not
evaluated because the specification does not define whether `^` means power,
XOR, or another operation.

## Build

GCC or Clang on Linux/macOS:

```sh
cc -std=c11 -Wall -Wextra -pedantic -O2 cfabric.c -o cfabric.exe
```

MinGW-w64 on Windows:

```powershell
 gcc -std=c11 -Wall -Wextra -pedantic -O2 cfabric.c -o cfabric.exe
```

Or run:

```sh
make
```

## Generate a deterministic world

```sh
./cfabric.exe \
  --seed 42 \
  --width 1200 \
  --height 800 \
  --canvas-count 6 \
  --canvas-partition-count 12 \
  --world-name world-42 \
  --output world-42.json
```

The same seed and the same generation arguments produce byte-identical JSON.
A direct generated world always contains `world.seed`, stored as a decimal
string so the full unsigned 64-bit value is preserved.

Other interfaces inherited from the configurator pattern:

```sh
./cfabric.exe --sample-config cfabric.example.conf
./cfabric.exe --config cfabric.example.conf
./cfabric.exe --ui
./cfabric.exe --help
```

## Validate and render

SVG requires only Python 3's standard library:

```sh
python3 cfabric.py world-42.json -o world-42.svg --show-points --labels
```

PNG uses Pillow when available:

```sh
python3 cfabric.py world-42.json -o world-42.png --scale 1.5
```

Validation without rendering:

```sh
python3 cfabric.py world-42.json --validate-only
```

The Python validator recomputes counts, references, closure, axis alignment,
canvas separation, point-line contacts, crossings, and overlaps. It does not
trust the JSON `validation` flag.

## Compose seedless worlds

Automatic non-colliding horizontal placement:

```sh
python3 clyaers.py world-a.json world-b.json \
  --layout horizontal --gap 24 \
  --collision reject \
  --output joined.json \
  --render joined.svg
```

Explicit overlay offsets are repeated in input order:

```sh
python3 clyaers.py world-a.json world-b.json \
  --layout overlay \
  --offset 0,0 --offset 300,120 \
  --collision reject \
  --output overlay.json
```

Collision policies:

- `reject` — fail on the first collision or clearance violation.
- `erase-points` — resolve point-only contacts by erasing the contact from the
  incoming layer and rebuilding complete rectangular fragments. It rejects
  line or area overlaps.
- `erase-regions` — subtract colliding lower-layer rectangular regions from the
  incoming layer and rebuild every surviving fragment as a complete valid
  canvas. Partitions wholly applicable to a fragment are reconstructed.

Composed JSON intentionally omits `world.seed`. It records layer order,
translations, and erasures, then passes the same independent zero-collision
validator used by the renderer.

## JSON outline

```text
schema
world                 # seeded for generated worlds; seedless for compositions
generator
valid_structure
counts
fabric_counts
objects.points
objects.straight_lines
canvases
canvas_partitions
validation
layers / erasures     # composed worlds only
```

## Checks

```sh
make check
```

This compiles the C source, verifies byte-for-byte seed determinism, validates
generated JSON, renders SVG, composes two worlds, and validates the seedless
result.
