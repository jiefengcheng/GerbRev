# GerbRev performance handoff

This branch is an isolated performance candidate for the standalone Gerber-only U05 CLI. The comparison baseline is `adadc7b5abcdd3efc8d94a3079e391a095c25338` on GerbRev `main`. The pinned synthetic suite is the portable way to reproduce the checks. The separate private evidence packet contains retained production-board operands, historical failures, measurement scripts and their original receipts.

## Start on a second machine

Follow the Python and binary-wheel setup in the [README](../README.md). The recording machine used Apple Silicon macOS, Python 3.14.5, Shapely 2.1.2 and GEOS 3.13.1. Keep the checkout, workspace and retained evidence at separate paths. Allow at least 5 GiB free for the standalone runtime, plus space for any retained evidence and new reports.

```sh
git clone --branch codex/retained-board-performance-handoff https://github.com/jiefengcheng/GerbRev.git
cd GerbRev
python3.14 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.lock
.venv/bin/python -m pip check

mkdir -p "$PWD/out"
work="$(mktemp -d "$PWD/out/check.XXXXXXXX")"
export PYTHONPATH="$PWD" TMPDIR="$work"
.venv/bin/python -B tests/run_trials.py "$work" --case round_and_junction --report
```

Use the printed report path to open the offline HTML overview. For an existing suite or job, `./u05-view "$job_or_suite" --output "$work/view"` writes a new report. Add `--links-only` for large jobs to browse their saved receipts and imagery.

Run all nine synthetic cases by dropping `--case round_and_junction`. Six exercise full output with all 47 operations, including both export verifiers, and three assert intentional halt diagnostics. Run the focused controls from the same repository root:

```sh
.venv/bin/python -B tests/check_trial.py "$work"
.venv/bin/python -B tests/check_legacy_export_reuse.py "$work"
.venv/bin/python -B tests/check_attachment_copper_index.py
.venv/bin/python -B tests/check_native_land_contacts.py
.venv/bin/python -B tests/check_spindle_coverage.py
.venv/bin/python -B tests/check_t05_execution_binding.py
```

## Changes to review

| Area | Entry points | Retained obligations |
| --- | --- | --- |
| First-pass and connected export | `src/gerber_u05/{legacy_export,exporter,worker}.py` | Construct once. Both verifier processes load the hash-bound Gerber bytes and ledger, independently reparse actual copper and run the geometry, attachment and corruption checks. |
| Local reference | `src/gerber_u05/reference_recipe.py` | Bind the native model and its parents to the construction. Each verifier checks the saved model and actual file through the existing native reference checks. |
| T05 attachment loops | `src/u05_board/{coverage,attachment_export}.py`, `src/junction_spindle_blend.py`, `src/gerber_u05/encoded_owner_projection.py` | Reuse immutable scene bindings, owner projections and spatially selected predecessors. Validate bindings and artifact reads. Preserve attachment outcomes, clearance, source-void policy and pin separation. |
| T01 owner geometry | `src/gerber_u05/{component_stages,pipeline}.py`, `src/{original_copper_owners,source_channel_scope}.py` | Reuse owner membership and unchanged predecessor geometry. Query current neighbor contributions when computing clearance. Preserve canonical and connected T01 clearance and pin predicates. |
| T02 rectangle geometry | `src/gerber_u05/{native_land_contacts,land_reconstruction}.py`, `src/stage_abi/{runtime,lands}.py`, `src/u04_board/search.py` | Preserve source-defined terminals and contact ports, accepted T04 as geometric entry, shared-gap policy, rectangle caps and all clearance checks. Reuse bound gap/contact preparation and completed scene material where applicable. |
| T04 widening and reports | `src/gerber_u05/ladder_width.py`, `src/{component_clearance,prepared_width_scene}.py` | Reuse selected envelopes and whole-route geometry. Remove a redundant part cache and assemble pair-report indexes in one pass. Preserve route decisions, smoothing, mandatory checks and final nominal and envelope audits. |

Stage order is T01 → T03 → T04 → T02 → T05 in both passes. The source catalogue owns feature identity, ownership, groups and source-defined protections. Every stage uses the hash-bound accepted predecessor for copper, walls and openings. Local reuse must respect changed neighbors, registered pin slots, and the distinction between model geometry and native reparse.

## Qualification boundary

The handoff run met all nine synthetic expectations in 152.3 seconds. All six delivery cases passed the 47 operations and produced a Gerber and 4× render. The three intentional halts and all six focused controls passed. The earlier matched comparisons and saved-operand benchmarks establish scoped parity. The private packet contains the saved board benchmark results. Compare only identical workloads and record setup, loop, end-of-loop validation, actual reparse, and wall/CPU times separately. The new branch has no fresh production-board timing or completed production-board qualification.

The next performance investigation should measure the complete T04 per-proposal checking path with the retained route order and accepted neighbor updates. Compare ordered decisions, blocker reasons, reports and final geometry. Time the route-check fallback and owner/pin checks separately. Run focused synthetic corruption and pin controls alongside that investigation. Preserve complete final validation and keep any full-board run outside the current handoff.
