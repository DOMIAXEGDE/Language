#!/usr/bin/env python3
"""
17.py

Book Sport external axiom testing kernel.

This kernel is deliberately modest: it does not claim to be a complete theorem
prover. It tests user-demanded candidate axioms relative to the fixed baseline
axioms embedded below, then uses 13.cpp and 14.cpp as the static-table and
Boolean-acceptance execution layer.

Standard mapping dictionary:
  a := accepted_information
  x := rejected_by_hard_barrier

Typical use:
  python 17.py init
  python 17.py compile
  python 17.py table
  python 17.py accept
  python 17.py prove "I can learn"
  python 17.py disprove "Proof by contradiction enables learning"
  python 17.py query "contradiction"
  python 17.py ui
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

APP = "17.py"
VERSION = "v1"
BASE_DIR = Path(__file__).resolve().parent

BASELINE_AXIOMS: List[Tuple[str, str]] = [('000', 'I exist'), ('001', 'I feel pain'), ('002', 'My pain can be increased by incompetence'), ('003', 'My pain can be decreased by competence'), ('004', 'I can learn'), ('005', 'Learning increases competence'), ('006', 'Contradiction increases incompetence'), ('007', 'Proof by contradiction does not enable learning'), ('008', 'Proof by error-free construction is learning'), ('009', 'Proof by contradiction is not learning'), ('010', 'Your level of competence is quantifiable'), ('011', 'Your level of incompetence is quantifiable'), ('012', 'Context changes your current level of competence'), ('013', 'The basis span of your competence can be optimized for all contexts'), ('014', 'Everyone is innocent'), ('015', 'Competence is a functional axial n-dimensional space'), ('016', 'Incompetence is not a functional axial n-dimensional space'), ('017', 'Since I exist, I can be treated as a living information-bearing system'), ('018', 'Since I feel pain, pain is a valid system signal'), ('019', 'Since incompetence can increase pain, incompetence is a negative system state'), ('020', 'Since competence can decrease pain, competence is a positive system state'), ('021', 'Since I can learn, my system state can be updated'), ('022', 'Since learning increases competence, learning is a valid update operation'), ('023', 'Since contradiction increases incompetence, contradiction is a corruption signal'), ('024', 'Since proof by error-free construction is learning, construction is the preferred proof engine'), ('025', 'Since proof by contradiction is not learning, contradiction is not a preferred learning engine'), ('026', 'Since competence is quantifiable, competence can be measured'), ('027', 'Since incompetence is quantifiable, incompetence can be measured'), ('028', 'Since context changes competence, competence is context-indexed'), ('029', 'Since competence can be optimized for all contexts, competence has a basis-span'), ('030', 'Since everyone is innocent, correction must not be treated as guilt'), ('031', 'Since competence is functional axial n-dimensional space, competence has dimensions'), ('032', 'Since incompetence is not functional axial n-dimensional space, incompetence lacks stable constructive basis'), ('033', 'The mind can ingest information through perception, language, memory, and action'), ('034', 'The mind can encode information as concepts, habits, images, words, and procedures'), ('035', 'The mind can index information by association, label, context, emotion, and purpose'), ('036', 'The mind can query stored information through attention, recall, questioning, and tool-use'), ('037', 'The mind can update stored information through learning'), ('038', 'The mind can validate stored information through error-free construction'), ('039', 'The mind can reject or quarantine contradictory information when it increases incompetence'), ('040', 'The mind can externalize information into tools, notes, diagrams, calendars, code, and environment'), ('041', 'The human environment can serve as auxiliary storage'), ('042', 'Human-made tools can serve as auxiliary memory, index, query, and validation systems'), ('043', 'The body can store competence as trained procedure'), ('044', 'Repetition can strengthen retrieval pathways when it increases competence'), ('045', 'Reflection can detect incompetence when pain, error, or contradiction appears'), ('046', 'Deliberate practice can transform incompetence into competence'), ('047', 'A context can be treated as a coordinate region inside competence-space'), ('048', 'A skill can be treated as an axis inside competence-space'), ('049', 'A habit can be treated as a repeated function over time'), ('050', 'A tool can be treated as an external operator that extends mental function'), ('051', 'A note can be treated as persistent external memory'), ('052', 'A diagram can be treated as spatial indexing of thought'), ('053', 'A calendar can be treated as temporal indexing of intention'), ('054', 'A checklist can be treated as procedural compression'), ('055', 'A question can be treated as a query operation'), ('056', 'An answer can be treated as a retrieved or constructed record'), ('057', 'A mistake can be treated as a detected incompetence marker'), ('058', 'Correction can be treated as a competence-restoring update'), ('059', 'Optimization can be treated as basis-span improvement across contexts'), ('060', 'The mental human-centric database is the union of mind, body, environment, and tools'), ('061', 'The purpose of the mental human-centric database is to reduce pain by increasing competence'), ('062', 'The governing rule of the database is to learn by error-free construction'), ('063', 'The final enforced target is complete competence under {014 + 015}'), ('064', 'Once true, always, true'), ('065', 'What is not true, cannot be done')]

COLUMNS: List[Tuple[str, str]] = [
    ("assert_baseline", "Declare the row axiom as an available baseline assertion."),
    ("prove_direct", "Attempt direct proof by exact baseline identity."),
    ("prove_derived", "Attempt constructive proof through an explicit derived baseline rule."),
    ("disprove_contradiction", "Attempt disproof by contradiction against a stored baseline axiom."),
    ("quarantine_unknown", "Reject or quarantine information not proven under the current baseline."),
    ("barrier_check", "Check that hard-barrier acceptance is enforced by Boolean truth arithmetic."),
    ("note_external", "Record an external user-demanded axiom test for review."),
]

FILES = {
    "baseline_json": "axiom_baseline.json",
    "row_headings": "axiom_rows.txt",
    "column_headings": "axiom_columns.txt",
    "config_13": "axiom_book_sport_13.fabric",
    "rules_14": "axiom_book_sport_14.rules",
    "facts_14": "axiom_book_sport_14.facts",
    "table": "axiom_book_sport_table.txt",
    "events": "axiom_book_sport_14.acceptance.events.txt",
    "events_normalized": "axiom_book_sport_14.acceptance.events.normalized.txt",
    "jsonl": "axiom_test_result.jsonl",
    "report": "axiom_test_report.md",
    "pending": "external_axioms.pending.txt",
}

ACCEPTED_SYMBOL = "a"
REJECTED_SYMBOL = "x"


@dataclass
class KernelResult:
    timestamp: float
    query: str
    mode: str
    verdict: str
    result_symbol: str
    candidate_state: str
    confidence: str
    baseline_ids: List[str]
    reason: str
    normalized_query: str
    matched_axioms: List[Dict[str, str]]


@dataclass
class EventRecord:
    state_symbol: str
    ordinal: int
    row_index: int
    column_index: int
    row_pointer: str
    column_pointer: str
    cell_pointer: str
    cell_identity_hash: str
    selected_rule: str
    selector_rank: str
    expression_hash: str
    boolean_result: str
    acceptance_state: str
    barrier_action: str
    integrity_ok: str
    event_hash: str
    accepted_information: str
    expression: str


def path(name: str) -> Path:
    return BASE_DIR / FILES[name]


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("n-dimensional", "n dimensional")
    text = text.replace("error-free", "error free")
    text = text.replace("competence-space", "competence space")
    text = text.replace("tool-use", "tool use")
    text = re.sub(r"\{\s*014\s*\+\s*015\s*\}", "014 015", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def row_pointer(axiom_id: str) -> str:
    return f"axiom_{axiom_id}"


def axiom_map() -> Dict[str, str]:
    return dict(BASELINE_AXIOMS)


def normalized_axiom_map() -> Dict[str, Tuple[str, str]]:
    return {normalize(text): (aid, text) for aid, text in BASELINE_AXIOMS}


def conclusion_map() -> Dict[str, Tuple[str, str]]:
    out: Dict[str, Tuple[str, str]] = {}
    for aid, text in BASELINE_AXIOMS:
        m = re.match(r"\s*Since\s+.+?,\s*(.+)\s*$", text, flags=re.IGNORECASE)
        if m:
            conclusion = m.group(1).strip()
            out[normalize(conclusion)] = (aid, text)
    return out


def make_manual_contradictions() -> Dict[str, Tuple[str, str, str]]:
    """Return normalized candidate -> (baseline id, baseline text, reason)."""
    pairs = [
        ("I do not exist", "000", "Direct negation of existence."),
        ("I cannot learn", "004", "Direct negation of learning capacity."),
        ("Learning does not increase competence", "005", "Negates baseline learning-to-competence relation."),
        ("Contradiction decreases incompetence", "006", "Reverses baseline contradiction-to-incompetence relation."),
        ("Contradiction does not increase incompetence", "006", "Negates baseline contradiction-to-incompetence relation."),
        ("Proof by contradiction enables learning", "007", "Contradicts the baseline rejection of contradiction as a learning engine."),
        ("Proof by contradiction is learning", "009", "Contradicts the baseline: proof by contradiction is not learning."),
        ("Proof by error-free construction is not learning", "008", "Negates construction-as-learning baseline."),
        ("Everyone is guilty", "014", "Contradicts the innocence axiom."),
        ("Correction must be treated as guilt", "030", "Contradicts the correction-not-guilt derived axiom."),
        ("Incompetence is a functional axial n-dimensional space", "016", "Contradicts the negative-space baseline for incompetence."),
        ("Competence is not a functional axial n-dimensional space", "015", "Negates the competence-space baseline."),
        ("Once true can become false", "064", "Contradicts permanence of truth under the baseline."),
        ("Once true, not always true", "064", "Contradicts permanence of truth under the baseline."),
        ("What is not true can be done", "065", "Contradicts the truth-gated action axiom."),
        ("False things can be done", "065", "Contradicts the truth-gated action axiom."),
    ]
    baseline = axiom_map()
    return {normalize(candidate): (bid, baseline[bid], reason) for candidate, bid, reason in pairs}


def direct_negative_candidate(norm: str) -> Optional[Tuple[str, str, str]]:
    """Catch simple negations: 'not <axiom>', 'it is not true that <axiom>'."""
    prefixes = ["not ", "it is not true that ", "it is false that "]
    lookup = normalized_axiom_map()
    for prefix in prefixes:
        if norm.startswith(prefix):
            stripped = norm[len(prefix):].strip()
            if stripped in lookup:
                aid, text = lookup[stripped]
                return aid, text, "Candidate is a direct explicit negation of a stored baseline axiom."
    return None


def evaluate_candidate(statement: str, mode: str = "test") -> KernelResult:
    norm = normalize(statement)
    baseline_lookup = normalized_axiom_map()
    derived_lookup = conclusion_map()
    manual_contra = make_manual_contradictions()

    matched: List[Dict[str, str]] = []

    if norm in baseline_lookup:
        aid, text = baseline_lookup[norm]
        matched.append({"id": aid, "text": text, "relation": "direct_baseline_identity"})
        return KernelResult(
            timestamp=time.time(), query=statement, mode=mode, verdict="PROVED",
            result_symbol=ACCEPTED_SYMBOL, candidate_state="accepted_information",
            confidence="exact", baseline_ids=[aid],
            reason="The candidate is exactly one of the stored baseline axioms after normalization.",
            normalized_query=norm, matched_axioms=matched,
        )

    if norm in derived_lookup:
        aid, text = derived_lookup[norm]
        matched.append({"id": aid, "text": text, "relation": "constructive_derived_conclusion"})
        return KernelResult(
            timestamp=time.time(), query=statement, mode=mode, verdict="PROVED",
            result_symbol=ACCEPTED_SYMBOL, candidate_state="accepted_information",
            confidence="derived", baseline_ids=[aid],
            reason="The candidate matches the conclusion of a stored constructive 'Since ..., ...' axiom.",
            normalized_query=norm, matched_axioms=matched,
        )

    if norm in manual_contra:
        aid, text, reason = manual_contra[norm]
        matched.append({"id": aid, "text": text, "relation": "contradiction"})
        return KernelResult(
            timestamp=time.time(), query=statement, mode=mode, verdict="DISPROVED",
            result_symbol=REJECTED_SYMBOL, candidate_state="rejected_by_hard_barrier",
            confidence="rule", baseline_ids=[aid], reason=reason,
            normalized_query=norm, matched_axioms=matched,
        )

    neg = direct_negative_candidate(norm)
    if neg:
        aid, text, reason = neg
        matched.append({"id": aid, "text": text, "relation": "explicit_negation"})
        return KernelResult(
            timestamp=time.time(), query=statement, mode=mode, verdict="DISPROVED",
            result_symbol=REJECTED_SYMBOL, candidate_state="rejected_by_hard_barrier",
            confidence="rule", baseline_ids=[aid], reason=reason,
            normalized_query=norm, matched_axioms=matched,
        )

    # Conjunctive constructive proof: A AND B is accepted only if every part is accepted.
    if " and " in norm:
        raw_parts = re.split(r"\s+and\s+", statement, flags=re.IGNORECASE)
        parts = [p.strip(" .;,") for p in raw_parts if p.strip(" .;,")]
        if len(parts) > 1:
            sub = [evaluate_candidate(part, mode="subproof") for part in parts]
            if all(item.verdict == "PROVED" for item in sub):
                mids = [bid for item in sub for bid in item.baseline_ids]
                matched = [m for item in sub for m in item.matched_axioms]
                return KernelResult(
                    timestamp=time.time(), query=statement, mode=mode, verdict="PROVED",
                    result_symbol=ACCEPTED_SYMBOL, candidate_state="accepted_information",
                    confidence="composite", baseline_ids=mids,
                    reason="Every conjunctive part was proven against the baseline.",
                    normalized_query=norm, matched_axioms=matched,
                )
            if any(item.verdict == "DISPROVED" for item in sub):
                mids = [bid for item in sub for bid in item.baseline_ids]
                matched = [m for item in sub for m in item.matched_axioms]
                return KernelResult(
                    timestamp=time.time(), query=statement, mode=mode, verdict="DISPROVED",
                    result_symbol=REJECTED_SYMBOL, candidate_state="rejected_by_hard_barrier",
                    confidence="composite", baseline_ids=mids,
                    reason="At least one conjunctive part was disproved against the baseline.",
                    normalized_query=norm, matched_axioms=matched,
                )

    # Lexical near-match support: not proof, just diagnostic.
    tokens = set(norm.split())
    scored: List[Tuple[int, str, str]] = []
    for aid, text in BASELINE_AXIOMS:
        base_tokens = set(normalize(text).split())
        overlap = len(tokens & base_tokens)
        if overlap >= max(3, min(6, len(tokens) // 2)):
            scored.append((overlap, aid, text))
    scored.sort(reverse=True)
    for _, aid, text in scored[:5]:
        matched.append({"id": aid, "text": text, "relation": "near_match_not_proof"})

    return KernelResult(
        timestamp=time.time(), query=statement, mode=mode, verdict="UNDECIDED_QUARANTINED",
        result_symbol=REJECTED_SYMBOL, candidate_state="rejected_by_hard_barrier",
        confidence="insufficient", baseline_ids=[m["id"] for m in matched],
        reason="The candidate is not proven or disproven by the current baseline. It is rejected by the hard barrier until a constructive rule or baseline extension is supplied.",
        normalized_query=norm, matched_axioms=matched,
    )


def write_text_file(target: Path, content: str) -> None:
    target.write_text(content, encoding="utf-8")


def write_json(target: Path, payload: object) -> None:
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def init_files() -> None:
    baseline_payload = {
        "schema": "book_sport_axiom_baseline_v1",
        "mapping_dictionary": {
            "a": "accepted_information",
            "x": "rejected_by_hard_barrier",
        },
        "purpose": "Baseline axioms for on-demand external axiom testing under Book Sport hard-barrier acceptance.",
        "axioms": [{"id": aid, "pointer": row_pointer(aid), "text": text} for aid, text in BASELINE_AXIOMS],
    }
    write_json(path("baseline_json"), baseline_payload)

    rows = []
    for aid, text in BASELINE_AXIOMS:
        safe = text.replace("\n", " ")
        rows.append(f"{row_pointer(aid)}=>{aid} {safe}")
    write_text_file(path("row_headings"), "\n".join(rows) + "\n")

    columns = [f"{pointer}=>{semantic}" for pointer, semantic in COLUMNS]
    write_text_file(path("column_headings"), "\n".join(columns) + "\n")

    config = f"""# 13.cpp config generated by 17.py
# Static baseline axiom Book Sport table.

kind=table
table_name=baseline_axiom_book_sport
row_headings_file={FILES['row_headings']}
column_headings_file={FILES['column_headings']}
row_role=baseline_axiom_pointer
column_role=axiom_test_instruction_pointer
cell_role=static_deferred_axiom_acceptance_cell
boolean_engine=14.cpp
boolean_contract=dynamic_boolean_truth_arithmetic
barrier_policy=hard_closed_until_boolean_acceptance
acceptance_state=deferred_to_14.cpp
cell_pointer_prefix=bs_axiom_cell
output_name=baseline_axiom_book_sport_table
output_target={FILES['table']}
separator=\\n
end
"""
    write_text_file(path("config_13"), config)

    rules = """# 14.cpp rules generated by 17.py
# Mapping dictionary: a := accepted_information, x := rejected_by_hard_barrier
# Rules are selected by specificity by 14.cpp.

default=false
column:assert_baseline=integrity_ok AND semantic_present AND baseline_loaded AND baseline_consistent
column:prove_direct=integrity_ok AND semantic_present AND direct_proof_enabled AND baseline_loaded
column:prove_derived=integrity_ok AND semantic_present AND derived_proof_enabled AND baseline_loaded
column:disprove_contradiction=integrity_ok AND semantic_present AND contradiction_detection_enabled AND hard_barrier
column:quarantine_unknown=integrity_ok AND hard_barrier AND quarantine_enabled
column:barrier_check=integrity_ok AND hard_barrier AND operator_authorized
column:note_external=integrity_ok AND semantic_present AND external_testing_enabled
"""
    write_text_file(path("rules_14"), rules)

    facts = """# 14.cpp facts generated by 17.py
# External Boolean premises supplied to the acceptance engine.

operator_authorized=true
baseline_loaded=true
baseline_consistent=true
direct_proof_enabled=true
derived_proof_enabled=true
contradiction_detection_enabled=true
quarantine_enabled=true
external_testing_enabled=true
"""
    write_text_file(path("facts_14"), facts)

    if not path("pending").exists():
        write_text_file(path("pending"), "# One external candidate axiom per line.\n")

    print("Initialized Book Sport axiom-testing files:")
    for key in ["baseline_json", "row_headings", "column_headings", "config_13", "rules_14", "facts_14", "pending"]:
        print(f"  {path(key)}")


def find_source(canonical: str, alternatives: Sequence[str]) -> Path:
    candidates = [BASE_DIR / canonical] + [BASE_DIR / item for item in alternatives]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find {canonical}. Tried: " + ", ".join(str(p) for p in candidates))


def compiler_command() -> str:
    for exe in ["g++", "c++", "clang++"]:
        if shutil.which(exe):
            return exe
    raise RuntimeError("No C++ compiler found. Install g++, c++, or clang++ and retry.")


def run(cmd: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(BASE_DIR), text=True, stdout=sys.stdout, stderr=sys.stderr, check=check)


def compile_cpp() -> None:
    cc = compiler_command()
    src13 = find_source("13.cpp", ["13(1).cpp"])
    src14 = find_source("14.cpp", ["14(1).cpp"])
    run([cc, "-std=c++17", "-Wall", "-Wextra", "-pedantic", "-O2", str(src13.name), "-o", "13"])
    run([cc, "-std=c++17", "-Wall", "-Wextra", "-pedantic", "-O2", str(src14.name), "-o", "14"])


def build_table() -> None:
    if not path("config_13").exists():
        init_files()
    exe = BASE_DIR / ("13.exe" if os.name == "nt" and (BASE_DIR / "13.exe").exists() else "13")
    if not exe.exists():
        compile_cpp()
    run([str(exe), "--config", FILES["config_13"], "--execute", "--overwrite", "--all", "--allow-large"])


def run_acceptance() -> None:
    if not path("table").exists():
        build_table()
    exe = BASE_DIR / ("14.exe" if os.name == "nt" and (BASE_DIR / "14.exe").exists() else "14")
    if not exe.exists():
        compile_cpp()
    run([
        str(exe),
        "--table", FILES["table"],
        "--rules", FILES["rules_14"],
        "--facts", FILES["facts_14"],
        "--execute", "--overwrite", "--all", "--allow-large",
        "--output-target", FILES["events"],
    ])


def parse_event_line(fields: List[str]) -> Optional[EventRecord]:
    if not fields or fields[0] != "event":
        return None
    # Current schema: event a/x ordinal ...
    if len(fields) >= 24 and fields[1] in {ACCEPTED_SYMBOL, REJECTED_SYMBOL}:
        return EventRecord(
            state_symbol=fields[1], ordinal=int(fields[2]), row_index=int(fields[3]), column_index=int(fields[4]),
            row_pointer=fields[5], column_pointer=fields[6], cell_pointer=fields[7], cell_identity_hash=fields[8],
            selected_rule=fields[9], selector_rank=fields[10], expression_hash=fields[11], boolean_result=fields[12],
            acceptance_state=fields[13], barrier_action=fields[14], integrity_ok=fields[15], event_hash=fields[21],
            accepted_information=fields[22], expression=fields[23],
        )
    # Legacy schema: event ordinal ... acceptance_state ...
    if len(fields) >= 23:
        acceptance_state = fields[12]
        symbol = ACCEPTED_SYMBOL if acceptance_state == "accepted_information" else REJECTED_SYMBOL
        return EventRecord(
            state_symbol=symbol, ordinal=int(fields[1]), row_index=int(fields[2]), column_index=int(fields[3]),
            row_pointer=fields[4], column_pointer=fields[5], cell_pointer=fields[6], cell_identity_hash=fields[7],
            selected_rule=fields[8], selector_rank=fields[9], expression_hash=fields[10], boolean_result=fields[11],
            acceptance_state=acceptance_state, barrier_action=fields[13], integrity_ok=fields[14], event_hash=fields[20],
            accepted_information=fields[21], expression=fields[22],
        )
    return None


def load_events(events_file: Optional[Path] = None) -> List[EventRecord]:
    target = events_file or path("events")
    if not target.exists():
        return []
    out: List[EventRecord] = []
    for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw or raw.startswith("#"):
            continue
        fields = next(csv.reader([raw], delimiter="\t", quotechar='"'))
        rec = parse_event_line(fields)
        if rec:
            out.append(rec)
    return out


def normalize_events() -> None:
    source = path("events")
    target = path("events_normalized")
    if not source.exists():
        raise FileNotFoundError(source)
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    out: List[str] = []
    inserted_mapping = False
    for line in lines:
        if line.startswith("# schema.event=event ordinal"):
            out.append("# mapping_dictionary.a=accepted_information")
            out.append("# mapping_dictionary.x=rejected_by_hard_barrier")
            out.append("# schema.event=event state_symbol ordinal row_index column_index row_pointer column_pointer cell_pointer cell_identity_hash selected_rule selector_rank expression_hash boolean_result acceptance_state barrier_action integrity_ok row_hash_ok column_hash_ok row_semantic_hash_ok column_semantic_hash_ok cell_identity_ok event_hash accepted_information expression")
            inserted_mapping = True
            continue
        if line.startswith("event\t"):
            fields = line.split("\t")
            if len(fields) >= 23 and fields[1] not in {ACCEPTED_SYMBOL, REJECTED_SYMBOL}:
                symbol = ACCEPTED_SYMBOL if fields[12] == "accepted_information" else REJECTED_SYMBOL
                out.append("\t".join([fields[0], symbol] + fields[1:]))
            else:
                out.append(line)
        else:
            out.append(line)
    if not inserted_mapping:
        out.insert(0, "# mapping_dictionary.x=rejected_by_hard_barrier")
        out.insert(0, "# mapping_dictionary.a=accepted_information")
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote normalized events: {target}")


def append_result(result: KernelResult) -> None:
    with path("jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
    write_report()


def write_report() -> None:
    records = []
    if path("jsonl").exists():
        for line in path("jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                records.append(json.loads(line))
    lines = [
        "# Book Sport External Axiom Test Report",
        "",
        "Mapping dictionary: `a := accepted_information`, `x := rejected_by_hard_barrier`.",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Time | Symbol | Verdict | Query | Baseline IDs | Reason |",
        "|---|---:|---|---|---|---|",
    ]
    for item in records[-200:]:
        when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item.get('timestamp', 0)))
        ids = ", ".join(item.get("baseline_ids", []))
        query = str(item.get("query", "")).replace("|", "\\|")
        reason = str(item.get("reason", "")).replace("|", "\\|")
        lines.append(f"| {when} | {item.get('result_symbol', '')} | {item.get('verdict', '')} | {query} | {ids} | {reason} |")
    path("report").write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_result(result: KernelResult) -> None:
    payload = asdict(result)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    append_result(result)


def query_events(term: str) -> None:
    if not path("events").exists():
        print("Acceptance events file not found. Running acceptance first.")
        run_acceptance()
    events = load_events()
    baseline = axiom_map()
    q = normalize(term)
    matches = []
    for ev in events:
        aid = ev.row_pointer.replace("axiom_", "") if ev.row_pointer.startswith("axiom_") else ""
        axiom_text = baseline.get(aid, "")
        haystack = normalize(" ".join([ev.row_pointer, ev.column_pointer, ev.accepted_information, ev.expression, axiom_text]))
        if q in haystack or all(part in haystack for part in q.split()):
            matches.append({
                "symbol": ev.state_symbol,
                "row": ev.row_pointer,
                "column": ev.column_pointer,
                "axiom": f"{aid} {axiom_text}".strip(),
                "acceptance_state": ev.acceptance_state,
                "selected_rule": ev.selected_rule,
                "event_hash": ev.event_hash,
            })
    print(json.dumps({"query": term, "matches": matches[:100], "count": len(matches)}, indent=2, ensure_ascii=False))


def batch_test(file_path: str) -> None:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(p)
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        result = evaluate_candidate(line, mode="batch")
        print_result(result)


def launch_ui() -> None:
    ui = find_source("15.py", ["15(1).py"])
    run([sys.executable, str(ui.name)], check=False)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Book Sport external axiom testing kernel.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="write baseline, row/column headings, 13 config, 14 rules/facts")
    sub.add_parser("compile", help="compile 13.cpp and 14.cpp")
    sub.add_parser("table", help="generate the static Book Sport axiom table with 13.cpp")
    sub.add_parser("accept", help="evaluate the static table with 14.cpp")
    sub.add_parser("all", help="init, compile, table, accept, normalize")
    sub.add_parser("normalize-events", help="normalize legacy 14.cpp events to explicit a/x event schema")
    sub.add_parser("ui", help="launch 15.py")

    p = sub.add_parser("prove", help="prove a candidate statement relative to the baseline")
    p.add_argument("statement")
    p = sub.add_parser("disprove", help="disprove a candidate statement relative to the baseline")
    p.add_argument("statement")
    p = sub.add_parser("test", help="test a candidate statement relative to the baseline")
    p.add_argument("statement")
    p = sub.add_parser("query", help="query generated 14.cpp events and baseline axiom text")
    p.add_argument("term")
    p = sub.add_parser("batch", help="test one candidate statement per line from a text file")
    p.add_argument("file")

    args = parser.parse_args(argv)

    if args.command == "init":
        init_files()
    elif args.command == "compile":
        compile_cpp()
    elif args.command == "table":
        build_table()
    elif args.command == "accept":
        run_acceptance()
    elif args.command == "normalize-events":
        normalize_events()
    elif args.command == "all":
        init_files(); compile_cpp(); build_table(); run_acceptance(); normalize_events()
    elif args.command == "prove":
        print_result(evaluate_candidate(args.statement, mode="prove"))
    elif args.command == "disprove":
        print_result(evaluate_candidate(args.statement, mode="disprove"))
    elif args.command == "test":
        print_result(evaluate_candidate(args.statement, mode="test"))
    elif args.command == "query":
        query_events(args.term)
    elif args.command == "batch":
        batch_test(args.file)
    elif args.command == "ui":
        launch_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
