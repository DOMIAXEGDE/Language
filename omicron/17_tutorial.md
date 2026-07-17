# 17.txt Tutorial for `basis_tensor`

This tutorial explains how to write `17.txt`, the JSON configuration file used by `16.cpp` / `basis_tensor`.

`17.txt` is not a programming language. It is a strict JSON configuration that defines:

- the six component alphabets,
- each component length policy,
- optional least-residue moduli,
- how many tensor rows to build,
- inline input strings or seed-file reconstruction settings,
- output preferences.

Important: JSON does not allow comments. Keep explanatory notes in a separate tutorial file like this one, and keep `17.txt` as valid JSON.

## 1. Fast Start

Compile:

```powershell
c++ -std=c++17 -Wall -Wextra -pedantic -O2 16.cpp -o basis_tensor
```

Create `17.txt`:

```json
{
  "version": 1,
  "instance_count": 2,
  "components": {
    "p": {
      "alphabet": "0123456789",
      "length": { "mode": "fixed", "value": 3 },
      "signed_mapping": "zigzag"
    },
    "q": {
      "alphabet": "0123456789",
      "length": { "mode": "fixed", "value": 2 },
      "positive_mapping": "id_plus_one"
    },
    "m": {
      "alphabet": "01",
      "length": { "mode": "variable", "min": 1, "max": 4 },
      "signed_mapping": "zigzag"
    },
    "g": {
      "alphabet": "abc",
      "length": { "mode": "fixed", "value": 2 },
      "positive_mapping": "id_plus_one"
    },
    "alpha": {
      "alphabet": "xyz",
      "length": { "mode": "fixed", "value": 2 },
      "signed_mapping": "zigzag"
    },
    "beta": {
      "alphabet": "01",
      "length": { "mode": "fixed", "value": 3 },
      "positive_mapping": "id_plus_one"
    }
  },
  "instances": [
    {
      "p": "123",
      "q": "45",
      "m": "101",
      "g": "ab",
      "alpha": "xy",
      "beta": "011"
    },
    {
      "p": "000",
      "q": "01",
      "m": "1",
      "g": "cc",
      "alpha": "zz",
      "beta": "111"
    }
  ],
  "seed": {
    "output_length": 1,
    "seed_file": "19.txt",
    "basis_output_path": "20.txt",
    "mode": "strict",
    "basis_policy": "ordered_with_repetition",
    "emit_generated_seed": true
  },
  "output": {
    "format": "json",
    "path": "basis_tensors.json"
  }
}
```

Validate:

```powershell
.\basis_tensor --config 17.txt --validate-only
```

Generate output:

```powershell
.\basis_tensor --config 17.txt
```

Generate output and write a seed record:

```powershell
.\basis_tensor --config 17.txt --write-seed-file 19.txt
```

Rebuild from seeds:

```powershell
.\basis_tensor --config 17.txt --from-seeds --seed-file 19.txt --basis-out 20.txt
```

## 2. The Big Picture

The program always uses this component order:

```text
p, q, m, g, alpha, beta
```

Each instance provides one string for each component. The program encodes each string into a raw integer id. The six raw ids form one row:

```text
I_i = [id_p, id_q, id_m, id_g, id_alpha, id_beta]
```

After all `N` instances, the raw dataset is:

```text
B_raw = [I_0, I_1, ..., I_{N-1}]
```

The program also computes least residues for each coordinate. Those rows form:

```text
B_residue = [T_0, T_1, ..., T_{N-1}]
```

The seed system addresses `B_raw`, not `B_residue`. This matters when residue moduli collapse different raw ids into the same residue.

## 3. JSON Skeleton

Every useful `17.txt` has this shape:

```json
{
  "version": 1,
  "instance_count": 1,
  "components": {
    "p": {},
    "q": {},
    "m": {},
    "g": {},
    "alpha": {},
    "beta": {}
  },
  "instances": [],
  "seed": {},
  "output": {}
}
```

Required:

- `components`
- all six component objects: `p`, `q`, `m`, `g`, `alpha`, `beta`
- `instance_count`, unless the instance count is inferred from inline instances

Required in normal generation mode:

- inline `instances`, or
- `--instance-file <path>`, or
- `--interactive`

Required in seed-build mode:

- `instance_count`
- valid component definitions
- seed settings or command-line seed options
- `19.txt` or another seed file supplied with `--seed-file`

## 4. Component Objects

Each component object defines a finite ordered alphabet and a length policy.

Fixed-length component:

```json
"p": {
  "alphabet": "0123456789",
  "length": { "mode": "fixed", "value": 3 },
  "signed_mapping": "zigzag"
}
```

Variable-length component:

```json
"m": {
  "alphabet": "01",
  "length": { "mode": "variable", "min": 1, "max": 4 },
  "signed_mapping": "zigzag"
}
```

Component fields:

- `alphabet`: ordered string of allowed byte symbols.
- `length.mode`: either `fixed` or `variable`.
- `length.value`: fixed byte length.
- `length.min`: minimum byte length for variable mode.
- `length.max`: maximum byte length for variable mode.
- `modulus`: optional positive decimal string or number for least-residue reduction.
- `signed_mapping`: informational field for signed slots.
- `positive_mapping`: informational field for positive denominator slots.

The program operates in byte-symbol mode. That means:

- alphabets are decoded JSON strings treated as byte sequences,
- input lengths are byte lengths,
- duplicate bytes in an alphabet are rejected,
- input strings containing bytes outside their component alphabet are rejected.

## 5. Length Policies

### Fixed Length

For alphabet size `r` and fixed length `L`, the domain size is:

```text
M = r^L
```

Example:

```json
"alphabet": "01",
"length": { "mode": "fixed", "value": 3 }
```

Valid strings:

```text
000
001
010
111
```

Invalid strings:

```text
00      length is 2, expected 3
0000    length is 4, expected 3
012     symbol 2 is not in alphabet 01
```

The ids are big-endian lexicographic ordinals:

```text
000 -> 0
001 -> 1
010 -> 2
111 -> 7
```

### Variable Length

For alphabet size `r` and allowed length interval `[L_min, L_max]`, the domain size is:

```text
M = sum(r^ell) for ell = L_min to L_max
```

Example:

```json
"alphabet": "ab",
"length": { "mode": "variable", "min": 1, "max": 2 }
```

Valid strings and ids:

```text
a  -> 0
b  -> 1
aa -> 2
ab -> 3
ba -> 4
bb -> 5
```

Different lengths do not collide because longer strings receive an offset for all shorter valid lengths.

## 6. The Six Slots

The component names have mathematical meaning:

```text
p, q, m, g, alpha, beta
```

They map into the symbolic Structure-1 expression:

```text
a_i = (P_i / Q_i) * ((M_i / G_i) ^ (Alpha_i / Beta_i))
```

Signed slots:

```text
p, m, alpha
```

These use zigzag mapping:

```text
raw id 0 -> 0
raw id 1 -> 1
raw id 2 -> -1
raw id 3 -> 2
raw id 4 -> -2
```

Positive denominator slots:

```text
q, g, beta
```

These use:

```text
positive value = raw id + 1
```

So `q`, `g`, and `beta` are always at least 1.

## 7. Residue Moduli

By default, each coordinate is reduced modulo its own raw domain size `M_c`.

Since the encoder already produces:

```text
0 <= raw_id < M_c
```

the default residue equals the raw id.

You can override a modulus:

```json
"p": {
  "alphabet": "0123456789",
  "length": { "mode": "fixed", "value": 2 },
  "signed_mapping": "zigzag",
  "modulus": "10"
}
```

If the raw id is `37`, the least residue is:

```text
37 mod 10 = 7
```

Use alternate moduli carefully. They can collapse distinct raw ids:

```text
7 mod 10 = 7
17 mod 10 = 7
```

The seed layer still reconstructs `B_raw`; it does not rely on residues.

## 8. Instances

Inline instances go in the `instances` array.

```json
"instances": [
  {
    "p": "123",
    "q": "45",
    "m": "101",
    "g": "ab",
    "alpha": "xy",
    "beta": "011"
  }
]
```

Rules:

- each instance must contain all six component names,
- every string must use only its component alphabet,
- every string must satisfy its component length policy,
- `instance_count` must match the number of inline instances.

The program records match-paste compatibility metadata for each component:

- `char_length`
- `unique_count`
- `unique_symbols`
- `preview`

These metadata fields do not determine the id. The id is determined only by alphabet order and length policy.

## 9. Seed Section

The `seed` object controls seed output and seed reconstruction.

```json
"seed": {
  "output_length": 2,
  "seed_file": "19.txt",
  "basis_output_path": "20.txt",
  "mode": "strict",
  "basis_policy": "ordered_with_repetition",
  "emit_generated_seed": true
}
```

Fields:

- `output_length`: canonical generated seed length, from 1 to 6.
- `seed_file`: default seed input path for `--from-seeds`.
- `basis_output_path`: default text output path for seed-build mode.
- `mode`: `strict` or `wrap`.
- `basis_policy`: must be `ordered_with_repetition`.
- `emit_generated_seed`: informational setting for generated seed metadata.

### Strict Seed Mode

Strict mode preserves exact address semantics.

A seed is valid only if:

- every digit is less than the computed seed radix `W_k`,
- the decoded address is less than the basis-address-space size `S`.

Strict mode is the default and is recommended for reproducible exact work.

### Wrap Seed Mode

Wrap mode accepts any nonnegative seed integers and reduces the decoded address:

```text
K = K_seed mod S
```

The output reports both:

- `K_seed`, the decoded source address,
- `K`, the effective wrapped address.

## 10. 19.txt Seed File Format

`19.txt` contains one seed sequence per non-empty, non-comment line.

Valid examples:

```text
0
42
0 5
1, 2, 3
[0, 0, 0, 0, 0, 17]
```

Comments:

```text
# this line is ignored
```

Rules:

- each seed sequence has 1 to 6 nonnegative decimal integers,
- spaces or commas may separate integers,
- optional square brackets are accepted,
- strict semantic validation depends on the current `17.txt` configuration and `N`.

## 11. Output Section

The `output` object controls normal generation output.

```json
"output": {
  "format": "json",
  "path": "basis_tensors.json"
}
```

Supported formats:

```text
json
text
```

You can override from the command line:

```powershell
.\basis_tensor --config 17.txt --json --out out.json
.\basis_tensor --config 17.txt --text --out out.txt
```

If no output path is supplied, output is printed to the console.

## 12. Normal Generation Workflow

Normal generation uses inline or interactive component strings.

Command:

```powershell
.\basis_tensor --config 17.txt
```

What happens:

1. The program validates all component definitions.
2. The program validates all input strings.
3. Each string is encoded into a raw id.
4. Raw ids form `B_raw`.
5. Least residues form `B_residue`.
6. Each raw row is ranked into a row ordinal.
7. The whole `B_raw` dataset is ranked into a basis address `K`.
8. The canonical seed sequence is emitted.
9. Structure-1 symbolic scalar expressions are emitted for each row.

Write the generated seed to `19.txt`:

```powershell
.\basis_tensor --config 17.txt --write-seed-file 19.txt
```

Append instead of replacing:

```powershell
.\basis_tensor --config 17.txt --write-seed-file 19.txt --append-seed-file
```

## 13. Seed-Build Workflow

Seed-build mode ignores inline instances and reconstructs datasets from seed addresses.

Command:

```powershell
.\basis_tensor --config 17.txt --from-seeds --seed-file 19.txt --basis-out 20.txt
```

What happens:

1. The program reads component definitions and `instance_count` from `17.txt`.
2. The program reads seed records from `19.txt`.
3. Each seed record is decoded into a basis address.
4. The basis address is unranked into row ordinals.
5. Each row ordinal is unranked into six raw ids.
6. Each raw id is decoded into canonical component strings.
7. Raw ids and residues are emitted as `B_raw` and `B_residue`.
8. One basis block is written per seed record.

If inline instances are present while `--from-seeds` is active, this implementation reports that they are ignored.

## 14. Minimal Tiny Configuration

This example keeps the finite row space small and easy to inspect.

```json
{
  "version": 1,
  "instance_count": 1,
  "components": {
    "p": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "signed_mapping": "zigzag" },
    "q": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "positive_mapping": "id_plus_one" },
    "m": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "signed_mapping": "zigzag" },
    "g": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "positive_mapping": "id_plus_one" },
    "alpha": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "signed_mapping": "zigzag" },
    "beta": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "positive_mapping": "id_plus_one" }
  },
  "instances": [
    { "p": "0", "q": "1", "m": "1", "g": "0", "alpha": "1", "beta": "0" }
  ],
  "seed": {
    "output_length": 1,
    "seed_file": "19.txt",
    "basis_output_path": "20.txt",
    "mode": "strict",
    "basis_policy": "ordered_with_repetition",
    "emit_generated_seed": true
  },
  "output": {
    "format": "text",
    "path": "tiny_output.txt"
  }
}
```

Because every component has domain size 2:

```text
R = 2 * 2 * 2 * 2 * 2 * 2 = 64
```

With `instance_count = 1`:

```text
S = R^N = 64^1 = 64
```

With seed length 1:

```text
W_1 = 64
```

## 15. Variable-Length Example

This example uses variable length for `m`.

```json
"m": {
  "alphabet": "ab",
  "length": { "mode": "variable", "min": 1, "max": 2 },
  "signed_mapping": "zigzag"
}
```

Allowed `m` values:

```text
a
b
aa
ab
ba
bb
```

Rejected `m` values:

```text
empty string, because min is 1
aaa, because max is 2
ac, because c is outside alphabet ab
```

To allow the empty string, use:

```json
"length": { "mode": "variable", "min": 0, "max": 2 }
```

Then `""` is valid JSON for an empty string instance value.

## 16. Alternate Modulus Example

This configuration makes `p` residues wrap modulo 5.

```json
"p": {
  "alphabet": "0123456789",
  "length": { "mode": "fixed", "value": 2 },
  "signed_mapping": "zigzag",
  "modulus": "5"
}
```

Examples:

```text
raw id 00 -> 0, residue 0
raw id 05 -> 5, residue 0
raw id 19 -> 19, residue 4
```

This is useful when you want displayed least-residue tensors in a smaller coordinate domain, while still preserving full reconstruction through `B_raw` and the seed address.

## 17. Real-Admissibility Notes

For each row, the program builds:

```text
a_i = (P_i / Q_i) * ((M_i / G_i) ^ (Alpha_i / Beta_i))
```

It emits symbolic text and structured JSON fields. It does not rely on floating point as the authoritative value.

Status values:

- `real_exact_symbolic`: valid under ordinary real arithmetic and represented exactly.
- `real_approx_available`: reserved for exact symbolic plus finite numeric approximation.
- `complex_required`: ordinary real arithmetic is insufficient.
- `undefined_real_expression`: undefined under the program's real-arithmetic rules.

Key cases:

```text
zero base, negative exponent -> undefined_real_expression
zero base, zero exponent     -> undefined_real_expression
zero base, positive exponent -> real_exact_symbolic
positive base                -> real_exact_symbolic
negative base, reduced exponent denominator odd  -> real_exact_symbolic
negative base, reduced exponent denominator even -> complex_required
```

## 18. Common Commands

Print a generated sample config:

```powershell
.\basis_tensor --sample-config
```

Validate only:

```powershell
.\basis_tensor --config 17.txt --validate-only
```

Generate JSON:

```powershell
.\basis_tensor --config 17.txt --json --out result.json
```

Generate text:

```powershell
.\basis_tensor --config 17.txt --text --out result.txt
```

Override instance count for seed-build mode or when the supplied instances match the override:

```powershell
.\basis_tensor --config 17.txt --instances 3
```

In normal inline-instance mode, `--instances 3` requires exactly three instance objects. If `17.txt` contains two inline instances and you override to three, validation fails by design.

Use seed length 2:

```powershell
.\basis_tensor --config 17.txt --seed-length 2
```

Build from a custom seed file:

```powershell
.\basis_tensor --config 17.txt --from-seeds --seed-file custom_19.txt --basis-out custom_20.txt
```

Use wrap mode:

```powershell
.\basis_tensor --config 17.txt --from-seeds --seed-mode wrap
```

Run built-in tests:

```powershell
.\basis_tensor --self-test
```

## 19. Validation Checklist

Before running, check:

- `17.txt` is valid JSON.
- Every JSON string uses valid escapes.
- All six components are present.
- Each alphabet is non-empty.
- No alphabet has duplicate decoded bytes.
- Every fixed length is nonnegative.
- Every variable length has `min <= max`.
- Every optional `modulus` is a positive decimal integer.
- Every instance contains `p`, `q`, `m`, `g`, `alpha`, and `beta`.
- Every instance string uses only bytes from its component alphabet.
- Every instance string satisfies its component length policy.
- `instance_count` matches the number of inline instances in normal mode.
- `seed.output_length` is in `1..6`.
- `seed.mode` is `strict` or `wrap`.
- `seed.basis_policy` is `ordered_with_repetition`.

## 20. Troubleshooting

### "malformed JSON"

Your `17.txt` is not valid JSON.

Common causes:

- trailing commas,
- comments inside JSON,
- single quotes instead of double quotes,
- unescaped backslashes,
- unescaped newlines inside strings.

### "alphabet contains duplicate decoded byte symbol"

The alphabet repeats a byte.

Bad:

```json
"alphabet": "001"
```

Good:

```json
"alphabet": "01"
```

### "contains byte outside alphabet"

An instance string used a symbol that is not allowed by that component.

If alphabet is:

```json
"alphabet": "abc"
```

then this is invalid:

```json
"g": "ad"
```

because `d` is not in `abc`.

### "wrong fixed byte length"

The input length does not equal the fixed length.

If length is:

```json
"length": { "mode": "fixed", "value": 3 }
```

then `"01"` and `"0101"` are invalid.

### "strict seed validation failed"

The seed line is syntactically valid, but not valid for the current finite address space.

Fix options:

- change the seed record,
- use the matching `17.txt`,
- increase seed length only if you are generating new canonical seeds,
- use `--seed-mode wrap` if wrapping semantics are intentional.

## 21. Best Practices

Keep `17.txt` runnable:

- do not put comments in it,
- keep tutorial notes in a separate `.md` or `.txt` file,
- validate with `--validate-only` before generating outputs.

Keep finite domains understandable:

- start with small alphabets,
- start with short lengths,
- inspect `R`, `S`, and `W_k` before scaling up.

Preserve exact reconstruction:

- treat `B_raw` as the reconstruction-addressed dataset,
- treat `B_residue` as the displayed least-residue dataset,
- treat seed sequences as metadata that addresses `B_raw`, not as tensor coordinates.

Use strict seed mode for exact workflows:

```json
"mode": "strict"
```

Use wrap mode only when modular wrapping is part of the experiment:

```json
"mode": "wrap"
```

## 22. Seed-Only 17.txt Template

Use this when you want `17.txt` to define the finite universe and `19.txt` to define all generated datasets.

```json
{
  "version": 1,
  "instance_count": 2,
  "components": {
    "p": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "signed_mapping": "zigzag" },
    "q": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "positive_mapping": "id_plus_one" },
    "m": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "signed_mapping": "zigzag" },
    "g": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "positive_mapping": "id_plus_one" },
    "alpha": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "signed_mapping": "zigzag" },
    "beta": { "alphabet": "01", "length": { "mode": "fixed", "value": 1 }, "positive_mapping": "id_plus_one" }
  },
  "seed": {
    "output_length": 2,
    "seed_file": "19.txt",
    "basis_output_path": "20.txt",
    "mode": "strict",
    "basis_policy": "ordered_with_repetition",
    "emit_generated_seed": true
  },
  "output": {
    "format": "json",
    "path": "basis_tensors.json"
  }
}
```

Example `19.txt`:

```text
0
1
[1, 1]
```

Run:

```powershell
.\basis_tensor --config 17.txt --from-seeds
```

The program writes `20.txt` by default.
