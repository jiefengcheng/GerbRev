# Shared T02 preparation — isolated qualification, 2026-11-16

Branch: `codex/t02-shared-preparation`, based on `0fcf38791612c9ee3ad86504d94608f0195c4b5c`.
This changes preparation reuse, not rectangle eligibility, growth, clearance,
pin separation, remedy, export or acceptance rules. No client full-board run or
7,069-proposal replay was started. The normal application is not integrated.

## Ownership and invalidation

`T02Preparation` owns a bounded preparation lifetime for one exact accepted
predecessor and captured T02 policy. `run_t02` creates it around plan, construction
and verification. A caller can explicitly supply the same context to successive
tasks. Each task receives fresh mutable adapters/checkers and recomputes its
verdicts. Only immutable operands, spatial candidate lists and neighbor records
are reusable. Source grouping remains source-bound; actual copper comes from the
accepted predecessor.

The session binds the entire scene and policy by canonical SHA-256. It checks
that binding before and after each lease, validates retained caches, and closes
on a task failure. A changed predecessor/policy is rejected; changed geometry
operands miss the cache. There is no stale acceptance reuse.

* Geometry reads continue reading and hashing the actual artifact bytes. A weak
  alias maps byte hashes to immutable shapes already held by a spatial tree or
  caller. This avoids decoding the same shape again after decoded-LRU eviction.
* Spatial indexes use ordered exact geometry hashes (including SRID and precision)
  plus index options. Operand reordering invalidates positional neighbor lists.
  Spatial candidates are cached; exact predicates still execute.
* Shared-gap records bind the scene, gap policy, original/current operands and
  supplied owner-source operands. Stored canonical JSON has a checked hash;
  every consumer gets a fresh decoded copy, so editing a plan cannot poison it.
* Predecessor unions use the existing exact expression and operand order through
  the bounded geometry memo. No union pruning, regrouping or approximation.

The context can be handed to different worker threads **within one process**.
Leases serialize access. It is not shared memory across separate CLI processes,
not a persistent disk cache, and does not make existing process-global ownership
and pin state safe for concurrent jobs. A foreign-process lease fails explicitly.

Existing limits remain: 192 MiB geometry allowance (8 MiB reserved for weak-alias
bookkeeping), 32 MiB index allowance, 32 MiB geometry memo, 4 MiB query cache,
32 MiB native parse cache. Neighbor records have a separate 4 MiB/256-entry bound.
These are retained-cache estimates, not a process RSS limit. Oversized geometry
memo results fall back to exact recomputation. On this saved board the large
predecessor union exceeds the 32 MiB memo allowance and is rebuilt each task.

## Measured saved-data comparison

Input: saved 3020301113B accepted T04 scene used by legacy T02; 17,849 objects,
263 rectangle targets. Its saved T02 audit is PASS and binds the retained stage
artifact. Each arm performs three preparation tasks in separate serial worker
threads, with new adapter instances. Each task rereads/hashes all operands,
computes the complete gap records, makes five ordered neighborhood queries,
and assembles the complete predecessor copper union. No rectangle search runs.

| Scope | Fresh preparation per task | Shared preparation | Saving |
|---|---:|---:|---:|
| Three tasks, wall | 76.683 s | 50.049 s | 34.73% |
| Three tasks, CPU | 76.428 s | 49.779 s | 34.87% |
| Individual task wall | 24.853 / 24.856 / 26.947 s | 28.397 / 10.775 / 10.870 s | reuse benefits subsequent tasks |

All six tasks have exact canonical neighbor-record parity with the saved plan,
identical ordered query answers, and identical assembled copper WKB hashes.
The complete record contains 30 groups, 99 slots and 70 entry walls. Shared
preparation built it once, reused it twice, built the tested index once, and
reused 10 of 15 queries. It decoded 40,623 of 107,094 reads; 66,471 reused shapes.
The initial implementation without content-based index reuse decoded 105,084
shapes and built the index three times. Its separate timing is retained, not
combined with the final measurement. No end-to-end T02 speedup is inferred.

## Checks and reproduction

Focused tests cover different worker leases, decoded-cache eviction, ordered
index invalidation, changed predecessor/policy, record copy isolation, corrupted
records, and fresh clearance/pin checks. KEEP and safe growth pass; deliberately
unsafe growth fails with exactly matching full reports. Run:

```sh
PYTHONPATH=. python -B tests/test_t02_preparation.py
```

On the project Mac, use the project workspace/test preparation wrapper first.
Keep `TMPDIR` and every test output under the mounted LaCie workspace.

The saved-data profiler accepts explicit paths and refuses an existing output
directory or paths outside `GERBER_U05_WORKSPACE`:

```sh
PYTHONPATH=. python -B tests/profile_t02_preparation.py \
  --saved-job "$GERBER_U05_WORKSPACE/operator_routes/gerber_u05_incremental_legacy/20261112T060513Z-7885ede64b5d4b92bf8b50f543a6f41e/legacy" \
  --output "$GERBER_U05_WORKSPACE/t02_preparation_comparison_new"
```

Evidence directory on the source Mac:
`out/lacie_work/t02_shared_preparation.rUwdOhQS/`.
`indexed/RESULT.json` is the final preparation measurement; `UNIT_index.log`
contains six passing focused tests. `FINAL_VALIDATION.json` records final
synthetic qualification, hashes and paths. The profiler in `indexed/benchmark.py`
is the exact executed script; the checked-in utility changes only CLI/path setup.

Two tiny synthetic routes exercise rectangle ownership/growth and ordered
polarity, including both U05 passes and actual Gerber export/reparse. These
are bounded regression cases, not a client-board rerun:

```sh
PYTHONPATH=. python -B tests/run_trials.py "$GERBER_U05_WORKSPACE" \
  --case rectangle_terminal --case ordered_polarity
```

The first synthetic attempt correctly halted at resource inventory validation:
two previously committed agent ABI files were absent from `u05_resources.json`.
The manifest now includes their exact hashes. Both failed runs remain intact.
The initial tuple-key unit failure and unavailable legacy pytest launcher log
also remain. Historical `.DS_Store` custody findings remain explicit and unwaived;
this qualification neither removes nor promotes them.

## Agent call boundary

```python
policy = {"stage": "t02", "parameters": land_parameters("t02")}
with T02Preparation(accepted_scene, policy) as preparation:
    result = run_t02(store, accepted_scene, preparation=preparation)
    # A later authorized task may reuse the same session with the same binding.
    stats = preparation.diagnostics()
```

A cache hit authorizes operand reuse only. The caller must still perform every
required current-scene check, stage verification, actual export/reparse and
corruption control. Do not reuse the context for a changed accepted predecessor.
Do not run extra construction solely to demonstrate reuse; use the saved-data
profiler. Cross-process durable sharing is outside this isolated implementation.
