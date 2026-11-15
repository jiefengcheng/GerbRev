"""Exercise mid-pass persistence, evidence deduplication, and corruption detection."""
from pathlib import Path
import sys

from shapely.geometry import box
from replay_evidence import ReplayEvidence
from src.gerber_u05.t04_pass_state import PassState
from src.stage_abi.store import canonical, digest
from src.t04_incremental import IncrementalRoutes
from src.t04_settings import capture

root = Path(sys.argv[1])
mode = sys.argv[2]
store = ReplayEvidence(root / "runtime")
journal = PassState(store, root / "checkpoints", ["fixture"], marker_width=5)
source = {"a": box(0, 0, .10, .04), "b": box(.136, .076, .236, .116)}
fixed = [{"id": "fixed", "geometry": box(-.136, .076, -.036, .116), "trace_width_mm": .10}]
baseline = [dict(id=sid, original=g, candidate=g, verified_original_width_mm=.10)
            for sid, g in source.items()]
settings = capture()
widths = dict.fromkeys(source, .10)
checker = IncrementalRoutes(
    baseline, fixed, lambda sid, factor, envelope: source[sid].buffer((factor-1)*.05, quad_segs=32),
    settings, widths, resume=mode == "resume")
rungs = dict.fromkeys(source, 0)
entries = []
cursor = 0
if mode == "resume":
    state = journal.latest()
    cursor = state["prefix"]["cursor"]
    assert cursor == 1
    rungs = state["prefix"]["accepted_rungs"]
    entries = state["evaluations"]
    journal.restore(state, checker, settings, widths)
    assert store.get_json(entries[0]["report_ref"], kind="width-check")["passed"]
for i, (sid, rung) in enumerate([("a", 1), ("b", 1), ("b", 8)][cursor:], cursor):
    factor = settings.rung(widths[sid], rung)["factor"]
    report = checker.evaluate(sid, factor)
    ref = store.put_json("width-check", report)
    assert ref["sha256"] == digest(canonical(report))
    assert store.put_json("width-check", report) == ref
    entries.append(dict(index=i, report_ref=ref, passed=report["passed"]))
    if report["passed"]:
        checker.accept(sid, factor)
        rungs[sid] = rung
    if mode == "interrupt":
        journal.save(dict(cursor=i+1, accepted_rungs=rungs), entries, checker, number=1)
        sys.exit()
assert [entry["passed"] for entry in entries] == [True, True, False]
assert len(list((root / "runtime/artifacts").glob("width-check:*.gz"))) == 3
(root / "out.json").write_bytes(canonical(dict(entries=entries, rungs=rungs)))
if mode == "resume":
    ref = entries[-1]["report_ref"]
    artifact = root / "runtime/artifacts" / (ref["artifact_id"] + ".gz")
    raw = artifact.read_bytes()
    artifact.write_bytes(raw[:-1])
    try:
        store.get_json(ref, kind="width-check")
    except (EOFError, ValueError):
        pass
    else:
        raise AssertionError("Corruption accepted")
    finally:
        artifact.write_bytes(raw)
