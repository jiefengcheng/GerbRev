# Consolidated T02 reuse handoff

Both isolated optimizations are on `codex/t02-packed-predecessor`:

* `cef312f`: job-owned shared preparation, immutable geometry reuse, ordered
  spatial indexes and copied neighbor records across task leases.
* `2e0a0cb`: exact packed predecessor geometry when the native-object memo cannot
  retain the large union, within the same combined memo allowance.

This handoff consolidates code and existing qualification. It does not merge the
branch into the normal app, start a client-board run, run the 7,069-proposal
replay, or extend qualification to other stages. The code descends from the
previous T04 visibility/checkpoint work at `0fcf387`.

## Consolidated optimization path

The earlier [performance handoff](PERFORMANCE_HANDOFF.md) covers export/reference,
T01, T02 neighbor-index and T05 attachment work. The subsequent T04 work separates
accepted state, dependency witnesses and exact visibility operands, so restarting
need not rediscover the same prepared copper. Its [checkpoint qualification](T04_VISIBILITY_CHECKPOINTS.md)
measured seven saved proposals at 50.77 → 40.50 s wall (20.2%), with setup reported
separately; total measured process time was 185.27 → 174.14 s (about 6%). All 3,384
route geometry digests and complete tested reports matched. This is distinct
from the older full 7,069-proposal replay and is not a full-board speed forecast.

The two T02 slices extend that principle in-process: keep preparation alive
across tasks, then avoid repeated oversized construction through a bounded exact
representation. No acceptance rule was replaced with an approximate shortcut.

## What is measured

Saved 3020301113B data: the accepted T04 scene used by legacy T02, 17,849 objects
and 263 rectangle targets. Each comparison performs three serial preparation
tasks with fresh adapters. All operands are reread/hash-checked, complete shared
neighbor records are obtained, five target neighborhoods are queried, and the
complete predecessor copper union is assembled. No growth search runs.

| Comparison | Wall before → after | CPU before → after | Wall reduction |
|---|---:|---:|---:|
| Fresh preparation → shared context | 76.683 → 50.049 s | 76.428 → 49.779 s | 34.73% |
| Shared context → packed union reuse | 48.396 → 40.011 s | 48.347 → 39.964 s | 17.33% |

These are two separate comparisons. Do not add their percentages or present
76.683 → 40.011 seconds as a single measured end-to-end run. Later tasks in the
second comparison fall from 10.354/10.474 to 6.169/6.142 seconds. The first task
still prepares the operands and union; it is 27.547 versus 27.694 seconds.

Final candidate counts across three tasks: one spatial index, one complete
neighbor-record build, one exact union build, two packed restorations. Of
107,094 geometry reads, 66,471 reuse decoded immutable shapes; 40,623 decode.
The ordered neighbor record covers all 30 groups, 99 slots and 70 entry walls.

## Parity and qualification

Both saved-data comparisons have exact canonical neighbor-record parity with
the saved plan, identical ordered query answers and identical full copper WKB
hashes across all six tasks in each comparison.

Thirteen focused tests pass. They cover changed input/policy rejection, geometry
and index reuse after LRU eviction, index ordering, neighbor-record copy
isolation, corruption, fixed-precision fallback, shared-budget pressure, holes,
islands, SRID, and full clearance/pin-report parity including unsafe growth.

Two tiny synthetic routes (`rectangle_terminal`, `ordered_polarity`) each pass
all 47 operations, including both U05 passes and actual export/reparse. Compared
with `cef312f`, both final Gerbers, both renders, and each legacy/connected
`t02.json` artifact are byte-identical. These are synthetic route qualifications,
not a new client-board final verdict or an overall U05 speedup measurement.

The current aggregate memory limits and every geometry/clearance/pin/export check
remain. Packed union bytes borrow space from the existing 32 MiB geometry memo.
Retained-cache estimates are not a peak RSS guarantee. An additional bounded
4 MiB neighbor-record cache was introduced in the first optimization. The
192 MiB decoded-geometry allowance includes its 8 MiB weak-alias bookkeeping
reserve. The generic adapter's 32 MiB spatial index and 4 MiB query allowances
remain unchanged.

## Shared infrastructure: actual interfaces

| Component | Implemented interface | Binding / ownership |
|---|---|---|
| T02 task lifetime | `T02Preparation(scene, policy)` and `.task(scene, policy)` | Exact accepted predecessor and captured T02 policy; serialized leases; close on failure |
| Geometry reuse | `T02Resources.decode(body)` | Hash actual input bytes; reuse validated immutable shapes; weak aliases add no strong native ownership |
| Ordered spatial index | `T02Resources.index(geometries, kwargs)` | Ordered exact geometry hashes, precision/SRID and options; changed order invalidates positional results |
| Spatial candidate queries | Existing `Resources.query(...)` / `PreparedTree.query(...)` | Tree content token plus query envelope; exact predicates are still executed |
| Neighbor records | `neighbor_records(scene, original, current, source, policy, build)` | Complete scene/operand/owner/policy binding; canonical bytes plus hash; fresh JSON copy to every caller |
| Exact construction memo | Existing `GeometryMemo.construct(...)` | Named expression, ordered operands and parameters; no algebraic reordering |
| Large exact result | `PackedGeometry.pack(key, shape)`, `.validate()`, `.restore()` | Compressed EWKB, raw length/hash and restored geometry hash; rejects unsupported fixed precision |
| T02 union adapter | `predecessor_union(geometries, build)` | One packed predecessor per session; original computation on miss or size/precision fallback |

Normal T02 wiring is in `src/gerber_u05/pipeline.py:run_t02`. It owns the session
around plan, construction and verification. Shared-gap wiring is in
`src/u04_board/search.py:FastRectangleAdapter._shared_gap_records`. Exact union
reuse is in `src/prepared_land_scene.py:PreparedLandScene`.

A cache contains operands, not acceptance. Mutable adapters, proposed copper,
verdicts and rejection history remain task-owned. Source catalogue identity,
ownership and grouping remain ground truth; the accepted predecessor supplies
actual copper, walls and openings. Every mandatory current-scene check still
executes. No source grouping may grant a new local bridge exemption.

## Data structures and algorithm costs

The decoded geometry LRU is indexed by artifact-byte digest. Weak aliases map
that same digest to `(weakref(shape), exact_geometry_digest)`. The STRtree and
caller already retain their own operands, so an alias can find a live shape
without adding another strong owner. Dead weakrefs are removed only if still
the currently registered reference; Python object ID reuse is not trusted.

Ordered index keys are `(tuple(geometry_digest), sorted_options)`. A query cache
adds the immutable tree content token and query envelope and stores ordered
indices plus a digest. An index hit is valid only for the same ordered operands;
equal geometry sets in another order do not qualify. Hashing costs scale with
geometry bytes. Index construction typically scales as N log N and queries with
candidate count, but the worst case can still return N objects. These caches do
not guarantee sublinear geometric checking for dense boards.

Neighbor records use an OrderedDict LRU of canonical JSON bytes and SHA-256.
Each consumer decodes its own copy. This avoids repeated geometric discovery
while retaining O(record bytes) validation/copy work. Current T02 records bind
the entire scene and operand set; changing one dependency can invalidate the
complete record. Fine-grained record patching is a future extension, not an
implemented partial-update claim.

The construction memo key is `(binding, expression_name, ordered_operand_tokens,
parameters)`. The packed path retains one immutable record with compressed EWKB,
raw size, two content hashes and metadata seal. Restoration is linear in stored
and decoded byte volume and avoids another GEOS union. It does not change the
asymptotic cost of a first construction, nor the exact predicates consuming it.
The packed weight subtracts from the same memo allowance, evicting ordinary
entries before publication. Invalid input, unsupported precision and cache
pressure are separate cases: reject invalid/corrupt state; compute exactly for
unsupported representation or insufficient retention budget.

## Agent ABIs

Two versioned, machine-readable interfaces accompany the source comments:

* [T02 preparation ABI](../contracts/t02/preparation_agent_abi.json): implemented
  Python signatures, lifecycle, inputs, metrics, budgets, errors and explicit
  unsupported operations. An agent calls `run_t02(..., preparation=context)`
  without an outer lease, because that function acquires its own lease. For
  direct preparation-only tasks, use `with context.task(scene, policy)`.
* [Immutable preparation / agent-loop ABI](../contracts/shared/immutable_preparation_agent_abi.json):
  future adapter design for binding, preparation, proposing, checking, accepting,
  rejecting, checkpointing and finalization. It defines data records and
  invalidation rules, but installs no generic executor or T02 resume command.

Both are included in the hashed runtime resource inventory. Neither contract is
a command to run a board. A cache hit means an operand can be reused, not that a
proposal or manufacturing result passed. Source comments explain each container,
key, ownership boundary, validation point, fallback and cleanup path. This
consolidation changes comments/docs/contracts only; computational AST parity
with `2e0a0cb` is checked with docstrings removed. Historical qualification
receipts remain bound to their original code revisions.

## Applying the pattern to other steps

This table describes extension opportunities, not already installed behavior.
Do not instantiate `T02Preparation` with another stage: its stage guard rejects it.
Extract an appropriately bound stage context only after a bounded saved-data
qualification establishes which operands remain invariant.

| Stage / work | Candidate reusable operands | Invalidate when |
|---|---|---|
| T01 | Immutable owner geometry, unchanged clearance buffers and neighbor lists | Neighbor copper, radius/buffer policy, ownership or pin protections change |
| T03 | Accepted predecessor geometry, route templates and dependency index | Route identity/topology, accepted copper or checking policy changes |
| T04 | Prepared geometry, exact visibility operands and local pair dependencies | Either pair operand, dependency membership, accepted state or policy changes; retain existing pass/checkpoint guards |
| T02 | Implemented shared context, neighbor records and packed predecessor | Scene/policy mismatch rejects the lease; changed live operands miss/invalidate records |
| T05 / export | Immutable attachment/reference constructions and exact operand snapshots | Attachment identity, predecessor/reference copper, export grid/encoding or policy changes |

Use the following extension sequence:

1. Profile a few saved tasks and separate setup, construction, local checks and
   complete final validation. Report CPU and wall separately.
2. Bind the exact accepted predecessor, source catalogue, policy and all live
   operand dependencies. Preserve ordered lists wherever output indices or
   exact GEOS byte representation depend on order.
3. Retain immutable operands once; query affected neighbors using the index.
   A changed query neighborhood must discover new neighbors, not merely reuse
   the previous list of hits. Leave exact predicates and final checks intact.
4. Give every task fresh mutable decision state. Reject stale bindings and
   corrupted records. A corruption failure is evidence, not a cache miss to hide.
5. For large immutable results, try a lossless representation within the existing
   allowance. If it does not fit or cannot preserve semantics, compute exactly.
6. Compare full reports, decisions and geometry bytes on saved positive and
   negative cases. Measure initial preparation separately from repeated-task
   savings. Do not extrapolate a small-loop speedup to total board runtime.

The implemented T02 session is **in-process only**. Worker threads explicitly
lease it serially. Separate CLI worker processes do not share its native GEOS
objects, and no persistent T02 checkpoint format is added. Existing process-global
owner/pin state is not made safe for parallel independent jobs. Future durable
sharing must separately bind runtime/implementation versions, input artifacts,
accepted state and cursor; restore complete dependencies and checks before reuse.
See the existing [incremental stage ABI design](../contracts/gerber_u05/incremental_stage_agent_abi.json)
and [T04 checkpoint implementation](T04_VISIBILITY_CHECKPOINTS.md). The generic
ABI remains a design, not a new implemented T02 resume command.

## Reproduction and evidence

See [shared preparation](T02_SHARED_PREPARATION.md) and
[packed predecessor](T02_PACKED_PREDECESSOR.md) for exact commands and separate
measurements. The saved profiler is `tests/profile_t02_preparation.py`:
`--baseline fresh` measures task preparation sharing, while `--baseline shared`
measures the packed union against the previous shared implementation.
The reference arm retains the historical JSON label `cold` in either mode.

Source Mac evidence folders under `out/lacie_work/`:

* `t02_shared_preparation.rUwdOhQS/`: `indexed/RESULT.json`,
  `FINAL_VALIDATION.json`, `COMMIT.json`, unit and synthetic logs.
* `t02_predecessor_reuse.7dkNooHP/`: `PROFILE.json`, `BENCHMARK.json`,
  `SYNTHETIC_PARITY.json`, `FINAL_VALIDATION.json`, `COMMIT.json` and logs.

The documentation publishes measurements and generic code. Client Gerbers,
geometry payloads and raw evidence archives remain in the retained workspace.
The first tuple-key test failure, unavailable historical pytest launcher and
resource-manifest startup failures remain intact. Historical `.DS_Store`
custody findings remain explicit and unwaived. No acceptance is promoted.
