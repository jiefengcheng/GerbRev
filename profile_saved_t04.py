"""Profile the actual T04 checker using a sealed continuation ledger."""
import argparse
import cProfile
from functools import wraps
import json
import fcntl
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import shapely
from src import hole_acceptance, t04_topology
from src.gerber_u05 import ladder_width, pipeline as p
from src.gerber_u05.ladder_continuation import restore_entry
from replay_evidence import ReplayEvidence
from src.gerber_u05.t04_pass_state import PassState
from src.gerber_u05.view_geometry import EvidenceStore
from src.gerber_u05.width_ledger import verify_width_ledger
from src.prepared_width_scene import PreparedWidthScene
from src.t04_incremental import IncrementalRoutes, OwnerDependencies
from src.u03_board.dependency import DependencyWidthScene

SOURCE = "207a51318f103190a4d61e76f4a0457fcfd11fd3db560c9439dd2f5f460f9b90"
T04 = "19be422696f74118686322c9bc0823b75a5eaeae97c84173a97554fc8036cc77"
HOLE_SNAPSHOT = "6c7d842557252f18b30fefee10c9186fd2dfda0bdabb1a655caaf8aa7c76f8ca"


class ReplayStore(EvidenceStore):
    def __init__(self, legacy, scratch):
        super().__init__(legacy)
        self.root = legacy / "runtime"
        self.output = ReplayEvidence(scratch / "runtime")

    def get(self, reference, *, kind=None):
        kind = kind or reference["artifact_id"].split(":", 1)[0]
        if (self.artifacts / reference["artifact_id"]).exists():
            return super().get(reference, kind=kind)
        return self.output.get(reference, kind=kind)

    def put(self, kind, data):
        return self.output.put(kind, data)

    def put_json(self, kind, value):
        return self.output.put_json(kind, value)


class SampleComplete(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--limit", type=int, default=7069)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=500)
    args = parser.parse_args()
    if args.checkpoint_every < 1:
        parser.error("--checkpoint-every must be positive")
    if not 1 <= args.limit <= 7069:
        parser.error("--limit must be between 1 and 7069")
    if (shapely.__version__, shapely.geos_version_string) != ("2.1.2", "3.13.1"):
        raise SystemExit("Expected Shapely 2.1.2 and GEOS 3.13.1")
    legacy = args.evidence / ("operator_routes/gerber_u05_incremental_legacy/"
                              "20261112T060513Z-7885ede64b5d4b92bf8b50f543a6f41e/legacy")
    registry = args.evidence / ("evidence/u05_3020301113B_20261111/three_pass_continuation/"
                                "legacy_grid_diagnostic/recovery_source/contracts/pin_separation/settings.json")
    workspace = p.configure()
    if not args.scratch.resolve().is_relative_to(workspace) or args.scratch.resolve().is_relative_to(args.evidence.resolve()):
        raise ValueError("Scratch must be under the selected workspace and outside retained evidence")
    args.scratch.mkdir(exist_ok=args.resume)
    run_lock = (args.scratch / "replay.lock").open("a")
    fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.resume and (args.scratch / "REPLAY_RESULT.json").exists():
        raise ValueError("T04_REPLAY_ALREADY_COMPLETED")
    store = ReplayStore(legacy, args.scratch)
    binding = p.load(legacy / "source.json")
    t04 = (legacy / "t04.json").read_bytes()
    if p.digest(t04) != T04 or binding["source_ref"]["sha256"] != SOURCE:
        raise ValueError("Saved source/T04 binding changed")
    saved = json.loads(t04)
    t03 = (legacy / "t03.json").read_bytes()
    for stage, checksum in (("t03", p.digest(t03)), ("t04", T04)):
        for mode in ("construct", "1", "2", "proof"):
            proof = p.load(legacy / "audits" / stage / (mode + ".json"))
            if (proof["status"], proof["source_sha256"], proof["candidate_sha256"]) != ("PASS", SOURCE, checksum):
                raise ValueError(f"Saved audit mismatch: {stage}/{mode}")
    scene = p.validate_scene(store, json.loads(t03)["output_scene_ref"])
    solution = saved["solution"]
    if saved["retained_prefix"]["completed_passes"] != 4:
        raise ValueError("Expected four completed passes")
    rungs = dict.fromkeys(solution["stable_route_order"], 0)
    continuation = []
    for item in solution["evaluations"]:
        if item["pass_number"] > 4:
            continuation.append(item)
        elif item["passed"]:
            rungs[item["route_id"]] = item["candidate"]["rung"]
    if sum(item["candidate"]["within_growth_limits"] for item in continuation) != 7069:
        raise ValueError("Unexpected saved continuation size")

    input_bindings = [
        (legacy / name).read_bytes()
        for name in ("T04_SETTINGS_SNAPSHOT.json", "T04_PASS_SCHEDULE.json")
    ]
    implementation = [p.digest(path.read_bytes()) for path in
                      (Path(__file__), Path(__file__).with_name("replay_evidence.py"))]
    implementation.extend(p.digest(path.read_bytes()) for path in
                          sorted((Path(__file__).parent / "src").rglob("*.py")))
    journal = PassState(store.output, args.scratch / "checkpoints", [
        SOURCE, T04, p.digest(t03), p.digest((legacy / "source.json").read_bytes()),
        p.digest(registry.read_bytes()), HOLE_SNAPSHOT,
        [p.digest(data) for data in input_bindings], implementation,
        shapely.__version__, shapely.geos_version_string,
    ], marker_width=5)
    resume = journal.latest()
    if args.resume and resume is None:
        raise ValueError("T04_REPLAY_CHECKPOINT_REQUIRED")

    phase = "setup"
    timing = {}
    checker = None
    checks = accepted = differences = caps = 0
    restored_exact = None
    final_exact = {}
    evidence = []
    saved_rungs = dict(rungs)
    checkpoint_number = resume["number"] if resume else 0
    status = "FAILED"
    error = None

    def timed(name, function):
        @wraps(function)
        def call(*a, **kw):
            wall, cpu = perf_counter(), process_time()
            try:
                return function(*a, **kw)
            finally:
                key = phase + "/" + name
                counts = timing.setdefault(key, dict(calls=0, wall_s=0., cpu_s=0.))
                counts["calls"] += 1
                counts["wall_s"] += perf_counter() - wall
                counts["cpu_s"] += process_time() - cpu
        return call

    original_load = p.load

    def archived_pin_policy(path):
        if Path(path) == p.ROOT / "contracts/pin_separation/settings.json":
            return original_load(registry)
        return original_load(path)

    def prepare_checker(*a, **kw):
        nonlocal checker
        if resume is not None:
            kw["resume"] = True
        checker = timed("prepare_incremental_checker", IncrementalRoutes)(*a, **kw)
        if checker.pin is not None:
            checker.pin.check = timed("pin_check", checker.pin.check)
        return checker

    def replay(widths, settings, evaluate, accept, *, pass_increments, prefix, checkpoint=None):
        nonlocal phase, checks, caps, accepted, differences, restored_exact
        if (prefix is not None or pass_increments != solution["pass_increments"]
                or sorted(widths) != checker.order or
                widths != {d["route_id"]: d["original_width_mm"] for d in solution["decisions"]}):
            raise ValueError("Proposal input differs from the saved ledger")
        nonlocal checkpoint_number
        cursor = 0
        phase = "restore_pass_4"
        if resume is None:
            restored = timed("restore_entry", restore_entry)(
                checker, {"accepted_rungs": saved_rungs}, settings, widths)
            restored_exact = restored == saved["retained_prefix"]["fresh_restored_entry_check"]
            if not restored_exact:
                (args.scratch / "ENTRY_DIFFERENCE.json").write_text(json.dumps(
                    sorted(k for k in set(restored) |
                           set(saved["retained_prefix"]["fresh_restored_entry_check"])
                           if restored.get(k) != saved["retained_prefix"]["fresh_restored_entry_check"].get(k))) + "\n")
        else:
            phase = "resume_checkpoint"
            progress = resume["prefix"]
            cursor = progress["cursor"]
            if not 0 <= cursor <= len(continuation):
                raise ValueError("T04_REPLAY_CURSOR_CHANGED")
            entries = iter(resume["evaluations"])
            for row in continuation[:cursor]:
                if not row["candidate"]["within_growth_limits"]:
                    caps += 1
                    continue
                entry = next(entries)
                if entry["index"] != row["index"]:
                    raise ValueError("T04_REPLAY_CHECKPOINT_ORDER_CHANGED")
                report = store.output.get_json(entry["report_ref"], kind="width-check")
                if report["passed"] != row["passed"]:
                    raise ValueError("T04_REPLAY_CHECKPOINT_DECISION_CHANGED")
                evidence.append(entry)
                checks += 1
                differences += entry["report_ref"]["sha256"] != row["check_sha256"]
                if row["passed"]:
                    accepted += 1
                    saved_rungs[row["route_id"]] = row["candidate"]["rung"]
            if (next(entries, None) is not None or saved_rungs != progress["accepted_rungs"]
                    or checks > args.limit):
                raise ValueError("T04_REPLAY_CHECKPOINT_BINDING_CHANGED")
            timed("restore_checkpoint", journal.restore)(resume, checker, settings, widths)
            restored_exact = progress["exact_restored_entry"]

        def save_checkpoint(next_cursor):
            nonlocal checkpoint_number
            checkpoint_number += 1
            progress = dict(accepted_rungs=saved_rungs, cursor=next_cursor,
                            exact_restored_entry=restored_exact)
            timed("publish_checkpoint", journal.save)(
                progress, evidence, checker, number=checkpoint_number)

        if resume is None:
            save_checkpoint(0)
        print(f"Pass 4 ready. Exact entry report: {restored_exact}. Starting at {checks}/{args.limit}.",
              flush=True)
        phase = "proposals"
        for position in range(cursor, len(continuation)):
            row = continuation[position]
            sid, candidate = row["route_id"], row["candidate"]
            factor = candidate["factor"]
            if candidate != settings.rung(widths[sid], candidate["rung"]):
                raise ValueError(f"Candidate parameters changed at attempt {row['index']}")
            checked = candidate["within_growth_limits"]
            if checked:
                if checks == args.limit:
                    raise SampleComplete
                store.output.last_report = None
                report = timed("proposal_check_and_report", evaluate)(sid, factor)
                ref = store.output.last_report
                if ref is None:
                    raise ValueError("T04_REPLAY_REPORT_REFERENCE_MISSING")
                if report["passed"] != row["passed"]:
                    p.save(args.scratch / "DECISION_MISMATCH.json", dict(attempt=row, report_ref=ref))
                    raise ValueError(f"Saved/new pass decision differs at attempt {row['index']}")
                evidence.append(dict(index=row["index"], report_ref=ref,
                                     saved_sha256=row["check_sha256"]))
                differences += ref["sha256"] != row["check_sha256"]
                checks += 1
                if row["passed"]:
                    timed("accept_neighbor_update", accept)(sid, factor)
                    saved_rungs[sid] = candidate["rung"]
                    accepted += 1
                if checks == 1 or checks % 100 == 0:
                    print(f"{checks}/{args.limit} checks, {accepted} accepted, {differences} report differences",
                          flush=True)
            else:
                caps += 1
            next_cursor = position + 1
            pass_complete = (next_cursor == len(continuation) or
                             continuation[next_cursor]["pass_number"] != row["pass_number"])
            if pass_complete or (checked and (checks % args.checkpoint_every == 0
                                             or checks == args.limit)):
                save_checkpoint(next_cursor)
        if checker.versions != solution["selected_scales"]:
            raise ValueError("Final factors differ from saved decisions")
        phase = "final_checks"
        return solution

    start_wall, start_cpu = perf_counter(), process_time()
    profiler = cProfile.Profile()
    try:
        if p.digest((legacy / hole_acceptance.SNAPSHOT).read_bytes()) != HOLE_SNAPSHOT:
            raise ValueError("Saved ordinary-hole policy differs from the sealed job")
        hole_policy = hole_acceptance.bind(legacy)
        print(f"Bound saved ordinary-hole policy: {hole_policy['ordinary_holes']}.", flush=True)
        timed("validate_saved_width_ledger", verify_width_ledger)(saved, store)
        print("Saved ledger validated. Initializing the accepted T03 scene.", flush=True)
        # The public checkout's pin registry omits customer declarations.
        # Initialize against the archived registry and check its original binding.
        with patch.object(p, "load", archived_pin_policy):
            timed("initialize_accepted_T03", p.initialize)(store, binding, scene)
        print("T03 scene ready. Preparing the T04 checker and restoring pass 4.", flush=True)
        with (
            patch.object(ladder_width, "IncrementalRoutes", prepare_checker),
            patch.object(ladder_width, "solve", replay),
            patch.object(p, "width_admission", return_value=saved["admission"]),
            patch.object(OwnerDependencies, "check", timed("owner_check", OwnerDependencies.check)),
            patch.object(DependencyWidthScene, "check", timed("dependency_fallback", DependencyWidthScene.check)),
            patch.object(PreparedWidthScene, "check", timed("scene_check", PreparedWidthScene.check)),
            patch.object(t04_topology, "check", timed("source_void_check", t04_topology.check)),
            patch.object(ReplayStore, "put_json", timed("report_serialization", ReplayStore.put_json)),
        ):
            result = profiler.runcall(ladder_width.run, store, scene)
        p.save(args.scratch / "REPLAY_RESULT.json", dict(
            output_scene_ref=result["output_scene_ref"], checks=result["checks"],
            proposal_evidence_refs=evidence))
        final_exact = {k: result["checks"][k] == saved["checks"][k] for k in ("nominal", "envelope")}
        status = ("COMPLETE_EXACT_REPLAY" if restored_exact and not differences
                  and all(final_exact.values()) and result["output_scene_ref"] == saved["output_scene_ref"]
                  else "COMPLETE_WITH_REPORT_DIFFERENCES")
    except SampleComplete:
        status = "BOUNDED_SAMPLE_COMPLETE"
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        profiler.dump_stats(args.scratch / "t04.prof")
        receipt = dict(status=status, source_sha256=SOURCE, saved_t04_sha256=T04,
                       wall_s=perf_counter() - start_wall, cpu_s=process_time() - start_cpu,
                       completed_checks=checks, accepted_neighbor_updates=accepted,
                       parameter_cap_rejections_seen=caps, nonidentical_reports=differences,
                       exact_restored_entry=restored_exact, exact_final_reports=final_exact,
                       preserved_hole_policy_sha256=HOLE_SNAPSHOT,
                       checker_diagnostics=checker.diagnostics() if checker is not None else None,
                       timings_inclusive=timing, error=error)
        path = args.scratch / "T04_PROFILE.json"
        path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(path, flush=True)


if __name__ == "__main__":
    main()
