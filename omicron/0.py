#!/usr/bin/env python3
"""
Canonical Truth-Table Colour Encoding (CTCE)

A deterministic mapping from a Boolean function's complete truth-table signature
to a reproducible colour value.

Core idea:
    Boolean behaviour -> canonical truth-table bits -> integer/hash -> colour

This file supports:
    - constants
    - unary gates
    - all 16 two-input Boolean functions
    - arbitrary n-input Boolean functions
    - simple combinational circuit composition
    - bounded sequential transition-table encoding
    - deterministic RGB/HEX colours
    - optional multi-swatch colour signatures for very large functions

Important limitation:
    A single 24-bit RGB colour has only 16,777,216 possible values.
    Therefore, for large Boolean functions, RGB can be reproducible but not
    globally unique. The canonical signature/hash remains the unique identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import product
from typing import Callable, Iterable, Mapping, Sequence


Bit = int
Bits = tuple[int, ...]
BoolFunc = Callable[..., int]


# ---------------------------------------------------------------------
# Basic validation
# ---------------------------------------------------------------------

def as_bit(x: int | bool) -> int:
    """Convert an integer/bool value to a strict Boolean bit."""
    return 1 if bool(x) else 0


def require_bits(bits: str) -> str:
    """Validate a truth-table bit string."""
    if not bits:
        raise ValueError("Truth-table bit string cannot be empty.")
    if any(ch not in "01" for ch in bits):
        raise ValueError("Truth-table bit string must contain only 0 and 1.")
    return bits


def infer_input_count_from_table(bits: str) -> int:
    """
    Infer n from a truth table of length 2^n.

    Example:
        len(bits) = 4  -> n = 2
        len(bits) = 8  -> n = 3
        len(bits) = 16 -> n = 4
    """
    bits = require_bits(bits)
    length = len(bits)

    if length & (length - 1) != 0:
        raise ValueError("Truth-table length must be a power of 2.")

    return length.bit_length() - 1


def input_rows(n: int) -> list[Bits]:
    """
    Canonical input ordering.

    For n = 2:
        00, 01, 10, 11

    For n = 3:
        000, 001, 010, 011, 100, 101, 110, 111
    """
    if n < 0:
        raise ValueError("Input count cannot be negative.")
    return [tuple(row) for row in product((0, 1), repeat=n)]


# ---------------------------------------------------------------------
# Colour conversion
# ---------------------------------------------------------------------

def int_to_rgb(value: int) -> tuple[int, int, int]:
    """Map an integer into 24-bit RGB by using its low 24 bits."""
    value = value & 0xFFFFFF
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB triple to #RRGGBB."""
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def hash_to_rgb(data: str | bytes, salt: str = "CTCE-RGB-v1") -> tuple[int, int, int]:
    """
    Deterministically map arbitrary data to RGB.

    This is reproducible, but not globally unique for all possible functions,
    because RGB has only 24 bits.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    digest = sha256(salt.encode("utf-8") + b":" + data).digest()
    value = int.from_bytes(digest[:3], "big")
    return int_to_rgb(value)


def truth_bits_to_direct_rgb(bits: str) -> tuple[int, int, int]:
    """
    Direct numeric colour mapping.

    This works especially cleanly for small truth tables. For the 16 two-input
    functions, it spreads the IDs 0..15 across the 24-bit RGB range.
    """
    bits = require_bits(bits)
    function_id = int(bits, 2)
    max_id = (1 << len(bits)) - 1

    if max_id == 0:
        return (0, 0, 0)

    scaled = round((function_id / max_id) * 0xFFFFFF)
    return int_to_rgb(scaled)


def truth_bits_to_hash_rgb(bits: str) -> tuple[int, int, int]:
    """Hash-based colour mapping for arbitrary-size truth tables."""
    bits = require_bits(bits)
    return hash_to_rgb(bits)


def truth_bits_to_multiswatch(bits: str, swatches: int = 4) -> list[str]:
    """
    Produce a longer deterministic colour signature.

    This reduces visual collision risk by giving several colours rather than
    one colour. It is useful for large circuits, PLAs, FPGAs, ASIC blocks, and
    bounded sequential machines.
    """
    bits = require_bits(bits)
    if swatches <= 0:
        raise ValueError("swatches must be positive.")

    digest = sha256(("CTCE-MULTI-v1:" + bits).encode("utf-8")).digest()
    needed = swatches * 3

    while len(digest) < needed:
        digest += sha256(digest).digest()

    colours: list[str] = []
    for i in range(swatches):
        chunk = digest[i * 3:(i + 1) * 3]
        colours.append(rgb_to_hex(tuple(chunk)))  # type: ignore[arg-type]

    return colours


# ---------------------------------------------------------------------
# BooleanFunction object
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class BooleanFunction:
    """
    Canonical representation of a Boolean function.

    The truth table is stored in canonical row order:
        0...00, 0...01, ..., 1...11
    """
    name: str
    input_count: int
    truth_bits: str

    def __post_init__(self) -> None:
        require_bits(self.truth_bits)
        expected = 1 << self.input_count
        if len(self.truth_bits) != expected:
            raise ValueError(
                f"{self.name}: expected truth table length {expected}, "
                f"got {len(self.truth_bits)}."
            )

    @property
    def function_id(self) -> int:
        return int(self.truth_bits, 2)

    @property
    def canonical_signature(self) -> str:
        return f"CTCE:v1:n={self.input_count}:bits={self.truth_bits}"

    @property
    def canonical_hash(self) -> str:
        return sha256(self.canonical_signature.encode("utf-8")).hexdigest()

    @property
    def direct_hex(self) -> str:
        return rgb_to_hex(truth_bits_to_direct_rgb(self.truth_bits))

    @property
    def hash_hex(self) -> str:
        return rgb_to_hex(truth_bits_to_hash_rgb(self.canonical_signature))

    @property
    def multiswatch(self) -> list[str]:
        return truth_bits_to_multiswatch(self.canonical_signature, swatches=4)

    def evaluate(self, *inputs: int | bool) -> int:
        if len(inputs) != self.input_count:
            raise ValueError(
                f"{self.name} expects {self.input_count} inputs, "
                f"got {len(inputs)}."
            )

        bits = tuple(as_bit(x) for x in inputs)
        index = int("".join(str(x) for x in bits), 2) if bits else 0
        return int(self.truth_bits[index])

    def table_rows(self) -> list[tuple[Bits, int]]:
        return [(row, self.evaluate(*row)) for row in input_rows(self.input_count)]


def from_callable(name: str, input_count: int, func: BoolFunc) -> BooleanFunction:
    """Create a BooleanFunction from a Python callable."""
    outputs: list[str] = []

    for row in input_rows(input_count):
        outputs.append(str(as_bit(func(*row))))

    return BooleanFunction(name=name, input_count=input_count, truth_bits="".join(outputs))


def from_truth_bits(name: str, bits: str) -> BooleanFunction:
    """Create a BooleanFunction directly from a truth-table bit string."""
    n = infer_input_count_from_table(bits)
    return BooleanFunction(name=name, input_count=n, truth_bits=bits)


# ---------------------------------------------------------------------
# Primitive gates
# ---------------------------------------------------------------------

GATES_0_INPUT: dict[str, BooleanFunction] = {
    "FALSE/0": BooleanFunction("FALSE/0", 0, "0"),
    "TRUE/1": BooleanFunction("TRUE/1", 0, "1"),
}

GATES_1_INPUT: dict[str, BooleanFunction] = {
    "BUFFER/IDENTITY": from_callable("BUFFER/IDENTITY", 1, lambda a: a),
    "NOT/INVERTER": from_callable("NOT/INVERTER", 1, lambda a: not a),
}

# All 16 two-input Boolean functions in canonical order:
# input rows are 00, 01, 10, 11
GATES_2_INPUT: dict[str, BooleanFunction] = {
    "FALSE": from_truth_bits("FALSE", "0000"),
    "AND": from_truth_bits("AND", "0001"),
    "A_AND_NOT_B": from_truth_bits("A_AND_NOT_B", "0010"),
    "A": from_truth_bits("A", "0011"),
    "NOT_A_AND_B": from_truth_bits("NOT_A_AND_B", "0100"),
    "B": from_truth_bits("B", "0101"),
    "XOR": from_truth_bits("XOR", "0110"),
    "OR": from_truth_bits("OR", "0111"),
    "NOR": from_truth_bits("NOR", "1000"),
    "XNOR/EQUIVALENCE": from_truth_bits("XNOR/EQUIVALENCE", "1001"),
    "NOT_B": from_truth_bits("NOT_B", "1010"),
    "A_OR_NOT_B": from_truth_bits("A_OR_NOT_B", "1011"),
    "NOT_A": from_truth_bits("NOT_A", "1100"),
    "NOT_A_OR_B": from_truth_bits("NOT_A_OR_B", "1101"),
    "NAND": from_truth_bits("NAND", "1110"),
    "TRUE": from_truth_bits("TRUE", "1111"),
}

ALIASES: dict[str, str] = {
    "IMPLY": "NOT_A_OR_B",
    "A_IMPLIES_B": "NOT_A_OR_B",
    "NON_IMPLY": "A_AND_NOT_B",
    "A_NOT_IMPLIES_B": "A_AND_NOT_B",
    "CONVERSE_IMPLY": "A_OR_NOT_B",
    "B_IMPLIES_A": "A_OR_NOT_B",
    "CONVERSE_NON_IMPLY": "NOT_A_AND_B",
    "B_NOT_IMPLIES_A": "NOT_A_AND_B",
    "PROJECTION_LEFT": "A",
    "PROJECTION_RIGHT": "B",
    "NOT_A_GATE": "NOT_A",
    "NOT_B_GATE": "NOT_B",
}


def get_gate(name: str) -> BooleanFunction:
    """Fetch a primitive gate by name or alias."""
    key = name.strip().upper().replace(" ", "_").replace("-", "_")

    for table in (GATES_0_INPUT, GATES_1_INPUT, GATES_2_INPUT):
        if key in table:
            return table[key]

    if key in ALIASES:
        return GATES_2_INPUT[ALIASES[key]]

    raise KeyError(f"Unknown gate: {name}")


# ---------------------------------------------------------------------
# Combinational circuit composition
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class CircuitNode:
    """
    A node in a combinational circuit.

    inputs:
        Each input is either:
            - an integer external-input index, e.g. 0 for x0, 1 for x1
            - a node name referring to an earlier node
    """
    name: str
    gate: BooleanFunction
    inputs: tuple[int | str, ...]


@dataclass(frozen=True)
class CombinationalCircuit:
    """
    A simple acyclic circuit evaluator.

    Nodes must be topologically ordered:
        every node can only depend on external inputs or earlier nodes.
    """
    name: str
    input_count: int
    nodes: tuple[CircuitNode, ...]
    outputs: tuple[int | str, ...]

    def evaluate(self, *external_inputs: int | bool) -> Bits:
        if len(external_inputs) != self.input_count:
            raise ValueError(
                f"{self.name} expects {self.input_count} inputs, "
                f"got {len(external_inputs)}."
            )

        ext = tuple(as_bit(x) for x in external_inputs)
        memory: dict[str, int] = {}

        def resolve(ref: int | str) -> int:
            if isinstance(ref, int):
                return ext[ref]
            return memory[ref]

        for node in self.nodes:
            args = tuple(resolve(ref) for ref in node.inputs)
            memory[node.name] = node.gate.evaluate(*args)

        return tuple(resolve(ref) for ref in self.outputs)

    def output_truth_bits(self) -> str:
        """
        Encode multi-output circuits by concatenating output bits per row.

        Example for 2 outputs:
            row 00 -> 01
            row 01 -> 11
            row 10 -> 10
            row 11 -> 00

            encoded bits -> 01111000
        """
        bits: list[str] = []

        for row in input_rows(self.input_count):
            output_bits = self.evaluate(*row)
            bits.extend(str(bit) for bit in output_bits)

        return "".join(bits)

    def colour_encoding(self) -> dict[str, object]:
        bits = self.output_truth_bits()
        signature = f"CTCE:v1:circuit={self.name}:n={self.input_count}:out={len(self.outputs)}:bits={bits}"
        return {
            "name": self.name,
            "input_count": self.input_count,
            "output_count": len(self.outputs),
            "truth_bits": bits,
            "canonical_signature": signature,
            "canonical_hash": sha256(signature.encode("utf-8")).hexdigest(),
            "hash_hex": rgb_to_hex(hash_to_rgb(signature)),
            "multiswatch": truth_bits_to_multiswatch(signature, swatches=4),
        }


# ---------------------------------------------------------------------
# Useful module constructors
# ---------------------------------------------------------------------

def make_half_adder() -> CombinationalCircuit:
    return CombinationalCircuit(
        name="HALF_ADDER",
        input_count=2,
        nodes=(
            CircuitNode("sum", GATES_2_INPUT["XOR"], (0, 1)),
            CircuitNode("carry", GATES_2_INPUT["AND"], (0, 1)),
        ),
        outputs=("sum", "carry"),
    )


def make_full_adder() -> CombinationalCircuit:
    return CombinationalCircuit(
        name="FULL_ADDER",
        input_count=3,
        nodes=(
            CircuitNode("a_xor_b", GATES_2_INPUT["XOR"], (0, 1)),
            CircuitNode("sum", GATES_2_INPUT["XOR"], ("a_xor_b", 2)),
            CircuitNode("a_and_b", GATES_2_INPUT["AND"], (0, 1)),
            CircuitNode("cin_and_axorb", GATES_2_INPUT["AND"], (2, "a_xor_b")),
            CircuitNode("carry", GATES_2_INPUT["OR"], ("a_and_b", "cin_and_axorb")),
        ),
        outputs=("sum", "carry"),
    )


def make_mux_2_to_1() -> CombinationalCircuit:
    """
    2-to-1 multiplexer:
        inputs: a, b, select
        output: a if select=0 else b
    """
    return CombinationalCircuit(
        name="MUX_2_TO_1",
        input_count=3,
        nodes=(
            CircuitNode("not_s", GATES_1_INPUT["NOT/INVERTER"], (2,)),
            CircuitNode("a_path", GATES_2_INPUT["AND"], (0, "not_s")),
            CircuitNode("b_path", GATES_2_INPUT["AND"], (1, 2)),
            CircuitNode("out", GATES_2_INPUT["OR"], ("a_path", "b_path")),
        ),
        outputs=("out",),
    )


# ---------------------------------------------------------------------
# Bounded sequential encoding
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class TransitionMachine:
    """
    Bounded sequential-machine representation.

    A sequential device is not fully described by a single ordinary
    combinational truth table unless its state is included.

    This representation encodes:
        current_state bits + input bits -> next_state bits + output bits

    That transition table can then be colour-encoded.
    """
    name: str
    state_bit_count: int
    input_count: int
    output_count: int
    transition: Callable[[Bits, Bits], tuple[Bits, Bits]]

    def transition_bits(self) -> str:
        bits: list[str] = []

        for state in input_rows(self.state_bit_count):
            for inputs in input_rows(self.input_count):
                next_state, outputs = self.transition(state, inputs)

                if len(next_state) != self.state_bit_count:
                    raise ValueError("Invalid next-state width.")

                if len(outputs) != self.output_count:
                    raise ValueError("Invalid output width.")

                bits.extend(str(as_bit(x)) for x in next_state)
                bits.extend(str(as_bit(x)) for x in outputs)

        return "".join(bits)

    def colour_encoding(self) -> dict[str, object]:
        bits = self.transition_bits()
        signature = (
            f"CTCE:v1:machine={self.name}:"
            f"state={self.state_bit_count}:in={self.input_count}:"
            f"out={self.output_count}:bits={bits}"
        )
        return {
            "name": self.name,
            "state_bit_count": self.state_bit_count,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "transition_bits": bits,
            "canonical_signature": signature,
            "canonical_hash": sha256(signature.encode("utf-8")).hexdigest(),
            "hash_hex": rgb_to_hex(hash_to_rgb(signature)),
            "multiswatch": truth_bits_to_multiswatch(signature, swatches=4),
        }


def make_t_flip_flop() -> TransitionMachine:
    """
    T flip-flop:
        state q
        input t
        next q = q XOR t
        output q_next
    """
    def transition(state: Bits, inputs: Bits) -> tuple[Bits, Bits]:
        q = state[0]
        t = inputs[0]
        q_next = q ^ t
        return (q_next,), (q_next,)

    return TransitionMachine(
        name="T_FLIP_FLOP",
        state_bit_count=1,
        input_count=1,
        output_count=1,
        transition=transition,
    )


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------

def describe_boolean_function(fn: BooleanFunction) -> dict[str, object]:
    return {
        "name": fn.name,
        "input_count": fn.input_count,
        "truth_bits": fn.truth_bits,
        "function_id": fn.function_id,
        "direct_hex": fn.direct_hex,
        "hash_hex": fn.hash_hex,
        "canonical_hash": fn.canonical_hash,
        "multiswatch": fn.multiswatch,
    }


def print_primitive_gate_table() -> None:
    print("name.truth_bits.function_id.direct_hex.hash_hex")

    for gate in (
        list(GATES_0_INPUT.values())
        + list(GATES_1_INPUT.values())
        + list(GATES_2_INPUT.values())
    ):
        print(
            f"{gate.name}."
            f"{gate.truth_bits}."
            f"{gate.function_id}."
            f"{gate.direct_hex}."
            f"{gate.hash_hex}"
        )


def print_encoding(title: str, encoding: Mapping[str, object]) -> None:
    print(title)
    for key, value in encoding.items():
        print(f"{key}: {value}")
    print()


# ---------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------

def main() -> None:
    print("CANONICAL TRUTH-TABLE COLOUR ENCODING")
    print()

    print("Primitive gates using '.' as delimiter:")
    print_primitive_gate_table()
    print()

    # Arbitrary Boolean function from callable:
    majority_3 = from_callable(
        "MAJORITY_3",
        3,
        lambda a, b, c: (a + b + c) >= 2,
    )

    print("Example arbitrary Boolean function:")
    print(describe_boolean_function(majority_3))
    print()

    # Composed circuit modules:
    half_adder = make_half_adder()
    full_adder = make_full_adder()
    mux = make_mux_2_to_1()

    print_encoding("Half-adder encoding:", half_adder.colour_encoding())
    print_encoding("Full-adder encoding:", full_adder.colour_encoding())
    print_encoding("2-to-1 MUX encoding:", mux.colour_encoding())

    # Bounded sequential device:
    tff = make_t_flip_flop()
    print_encoding("T flip-flop transition encoding:", tff.colour_encoding())


if __name__ == "__main__":
    main()
