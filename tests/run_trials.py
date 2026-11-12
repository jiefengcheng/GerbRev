"""Run small Gerber trials and check the behavior each case is designed to exercise."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from check_smoke import verify_delivery

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_bytes())


def check_round_and_junction(run, _delivery):
    t01 = read_json(run / "t01.json")
    kept, = t01["allocation"]["contained_keep_source_ids"]
    assert any(row["source_id"] == kept and row["decision"] == "KEEP" for row in t01["decisions"])
    assert t01["summary"]["grown"] > 0
    t05 = read_json(run / "t05.json")["summary"]
    assert t05["source_attachments"] == 3 and t05["grown"] >= 2
    return "T01 grew a round pad and kept a buried circle. T05 grew two junction routes."


def check_parallel_clearance(run, _delivery):
    t03 = read_json(run / "t03.json")["summary"]
    assert t03["trace_occurrences"] == 5 and t03["moved"] == 0
    t04 = read_json(run / "t04.json")["solution"]
    decisions = t04["decisions"]
    constrained = [row for row in decisions if row["blocking_reason"] == "NEW_COPPER_BELOW_FOREIGN_COMPONENT_GAP"]
    assert len(constrained) == 3
    assert all(0 < row["total_width_increase_mm"] < 0.030 for row in constrained)
    assert any(row["blocking_reason"] == "TOTAL_WIDTH_INCREASE_LIMIT"
               and abs(row["total_width_increase_mm"] - 0.030) < 1e-9 for row in decisions)
    return "T03 kept five native traces. T04 limited three parallel traces by clearance and one isolated trace by the 30 µm cap."


def check_rectangle_terminal(run, _delivery):
    source = read_json(run / "source.json")
    catalogue = read_json(run / "runtime/artifacts" / source["source_catalogue_ref"]["artifact_id"])
    terminal, = [row for row in catalogue["records"] if row["family"] == "source-short-rectangular-aperture-terminal/1"]
    assert terminal["growth_owner"] == "T02" and terminal["t04"] == "EXCLUDED_OTHER_SOURCE_FAMILY"
    t02 = read_json(run / "t02.json")
    assert any(row["source_id"] == terminal["source_id"] and row["status"] == "GROWN"
               for row in t02["candidate"]["decisions"])
    return "T02 grew the short square-aperture draw as a rectangle, with T04 excluded."


def check_ordered_polarity(_run, delivery):
    from shapely.geometry import Point
    from src.gerber_u05.gerber_source_profile import object_geometry, ordered
    from src.gerber_u05.legacy_export import parse

    exported = parse(Path(delivery["gerber"]).read_bytes())
    copper = ordered((object_geometry(obj)[0], obj.polarity_dark) for obj in exported.objects)
    assert copper.covers(Point(3.1, 2.5))
    assert not copper.intersects(Point(3.3, 2.5))
    assert copper.covers(Point(3.5, 2.5))
    return "Reparsed export preserved the copper rim, clear gap, and later dark island."


def check_leading_arc_no_rectangles(run, delivery):
    from gerbonara.graphic_objects import Arc
    from src.gerber_u05.legacy_export import parse

    source = read_json(run / "source.json")
    assert source["coordinate_oracle"]["source_format"] == "MM_L46_ABSOLUTE"
    t03 = read_json(run / "t03.json")["summary"]
    assert t03["trace_occurrences"] == 1 and t03["moved"] == 0
    for phase in ("legacy", "connected"):
        stage = read_json(run.parent / phase / "t02.json")
        assert stage["summary"]["rectangles"] == 0
        assert stage["verification"]["status"] == "NOT_APPLICABLE_EMPTY_NATIVE_RECTANGLE_INVENTORY"
    native = parse(Path(delivery["gerber"]).read_bytes())
    arc, = [obj for obj in native.objects if isinstance(obj, Arc)]
    assert (arc.x1, arc.y1, arc.x2, arc.y2) == (2, 0, 2.5, 0.5)
    return "The 4.6 input arc retained its endpoints in the reparsed Gerber. Both T02 passes verified an empty rectangle inventory."


def check_tight_parallel_keep(run, _delivery):
    for phase in ("legacy", "connected"):
        decisions = read_json(run.parent / phase / "t04.json")["solution"]["decisions"]
        blocked = [row for row in decisions if row["original_width_mm"] == 0.1]
        assert len(blocked) == 2
        for row in blocked:
            assert row["final_rung"] == 0 and row["total_width_increase_mm"] == 0
            assert row["blocking_reason"] == "NEW_COPPER_BELOW_FOREIGN_COMPONENT_GAP"
    return "Both 41 µm-gap traces kept their source width at rung zero in both passes."


@dataclass(frozen=True)
class ExpectedHalt:
    phase: str
    operation: str
    checks_passed: int
    diagnostic: str

    def verify(self, workspace, state, code):
        assert code == 1 and state["status"] == "HALTED" and state["phase"] == self.phase
        checks = state["checks"]
        assert checks[self.operation]["status"] == "FAIL"
        assert sum(row["status"] == "PASS" for row in checks.values()) == self.checks_passed
        assert len(checks) == self.checks_passed + 1 and "delivery" not in state
        diagnostic, = workspace.glob(f"operator_routes/gerber_u05/*/logs/{self.operation}.stderr.log")
        assert self.diagnostic in diagnostic.read_text().splitlines()[-1]
        return f"Expected halt at {self.phase}. {self.diagnostic}"


@dataclass(frozen=True)
class Trial:
    purpose: str
    verify: Callable | ExpectedHalt

    @property
    def outcome(self):
        return "HALTED" if isinstance(self.verify, ExpectedHalt) else "DELIVERED"


CASES = {
    "round_and_junction": Trial("T01 round-pad growth and KEEP, plus T05 junction growth", check_round_and_junction),
    "parallel_clearance": Trial("T03 trace retention and two distinct T04 widening limits", check_parallel_clearance),
    "rectangle_terminal": Trial("T02 ownership of a short square-aperture draw", check_rectangle_terminal),
    "ordered_polarity": Trial("Ordered dark, clear and restored copper in the final Gerber", check_ordered_polarity),
    "no_round_pads": Trial("T01 input with no eligible round pads",
        ExpectedHalt("legacy_t01", "legacy_t01_construct", 3, "NO_SOURCE_LANDS")),
    "leading_arc_no_rectangles": Trial("Leading-zero Gerber, native arc and empty T02 inventory", check_leading_arc_no_rectangles),
    "tight_parallel_keep": Trial("T04 retains both source widths at a 41 µm gap", check_tight_parallel_keep),
    "missing_eof": Trial("Truncated Gerber is rejected during source assembly",
        ExpectedHalt("assembly_source_assembly", "assembly_source_assembly_construct", 0, "missing mandatory M02 EOF marker")),
    "clear_clipped_trace": Trial("A clear operation bisects a native trace outside the supported family",
        ExpectedHalt("assembly_source_assembly", "assembly_source_assembly_construct", 0, "CLEAR_CLIPPED_TRACE_NEEDS_SEPARATE_FAMILY")),
}


def run_case(suite, case):
    trial = CASES[case]
    folder = suite / case
    source = folder / "input" / "top.art.gbr"
    source.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/trials" / f"{case}.gbr", source)
    workspace = folder / "work"
    workspace.mkdir()
    log = folder / "run.log"
    stderr = folder / "run.stderr.log"
    start = time.monotonic()
    print(f"RUN  {case}", flush=True)
    with log.open("xb") as out, stderr.open("xb") as err:
        result = subprocess.run(
            [str(ROOT / "u05"), "--trial", str(source), "--workspace", str(workspace)],
            env={**os.environ, "U05_PYTHON": sys.executable}, stdout=out, stderr=err,
        )
    state = {}
    try:
        lines = log.read_text().splitlines()
        assert lines, "CLI produced no status record"
        state = json.loads(lines[-1])
        if isinstance(trial.verify, ExpectedHalt):
            detail = trial.verify.verify(workspace, state, result.returncode)
        else:
            assert result.returncode == 0, f"Unexpected CLI exit {result.returncode}"
            state = verify_delivery(log)
            detail = trial.verify(Path(state["run"]), state["delivery"])
        verdict = "PASS"
    except (AssertionError, OSError, ValueError, KeyError, TypeError) as error:
        verdict = "FAIL"
        detail = str(error) or "Case-specific expectation failed"
    elapsed = time.monotonic() - start
    print(f"{verdict} {case} ({elapsed:.1f}s). {detail}", flush=True)
    return {
        "case": case, "purpose": trial.purpose, "expected": trial.outcome,
        "verdict": verdict, "detail": detail, "seconds": elapsed,
        "exit_code": result.returncode, "job_status": state.get("status"), "phase": state.get("phase"),
        "checks_passed": sum(row["status"] == "PASS" for row in state.get("checks", {}).values()),
        "delivery": state.get("delivery"),
        "stdout": str(log.relative_to(suite)), "stderr": str(stderr.relative_to(suite)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, nargs="?", help="Existing directory for trial artifacts")
    parser.add_argument("--list", action="store_true", help="List the cases and their expected outcomes")
    parser.add_argument("--case", action="append", choices=CASES, help="Run one case, repeat for multiple cases")
    parser.add_argument("--report", action="store_true", help="Build the offline visual suite report after the trials")
    args = parser.parse_args()
    if args.list:
        for name, trial in CASES.items():
            print(f"{name:<26} {trial.outcome:<10} {trial.purpose}")
        return 0
    if args.workspace is None:
        parser.error("workspace is required when running trials")
    suite = Path(tempfile.mkdtemp(prefix="u05_synthetic_trials.", dir=args.workspace.resolve(strict=True)))
    print(f"Trial files and logs are in {suite}", flush=True)
    start = time.monotonic()
    cases = list(dict.fromkeys(args.case or CASES))
    results = [run_case(suite, case) for case in cases]
    elapsed = time.monotonic() - start
    passed = sum(row["verdict"] == "PASS" for row in results)
    receipt = suite / "SUITE.json"
    receipt.write_text(json.dumps({
        "schema": "u05-synthetic-trials/1", "seconds": elapsed, "results": results,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{passed}/{len(results)} expectations passed in {elapsed:.1f}s. {receipt}", flush=True)
    report_code = 0
    if args.report:
        report = subprocess.run(
            [str(ROOT / "u05-view"), str(suite), "--output", str(suite.with_name(suite.name + "-view"))],
            env={**os.environ, "U05_PYTHON": sys.executable},
        )
        report_code = report.returncode
    return int(passed != len(results) or report_code != 0)


if __name__ == "__main__":
    raise SystemExit(main())
