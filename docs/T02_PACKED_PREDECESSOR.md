# T02 exact predecessor reuse follow-up — 2026-11-16

Isolated branch `codex/t02-packed-predecessor`, based on the reviewed shared
preparation commit `cef312f`. No client-board run, full proposal replay,
normal-app integration or remote push is part of this qualification.

## Cost identified

The saved 3020301113B preparation profile found that the complete ordered
predecessor copper union was still computed on every task. Two measured union
calls took 4.384 and 4.347 seconds wall. Its EWKB contains 21,630,568 bytes;
the native geometry memo's estimated weight exceeds its 32 MiB limit, so the
previous implementation correctly declined to retain it.

Lossless level-1 compression produces 16,028,798 bytes in 0.248 seconds. Restoring
it and comparing exact EWKB took 0.063 seconds in the initial probe. This is a
representation cache only: there is no change to polygons, holes, islands,
contour ordering, geometry precision or growth policy.

## Implementation and bounded ownership

The shared T02 context still executes the exact original ordered GEOS union on
a cache miss. Small results use the existing native geometry memo. An oversized
result can instead be stored as a single immutable `PackedGeometry` record.
The record binds the exact ordered operand hashes, predecessor and policy,
compressed-byte hash, decoded-byte hash, decoded byte count and geometry hash.

The compressed record borrows from the **same 32 MiB memo allowance**. It is not
an additional cache. The saved-board record uses 16,029,822 estimated bytes,
leaving 17,524,610 bytes for ordinary geometry memo entries. Normal LRU entries
are evicted if necessary. Only one predecessor record is retained; changed
operands invalidate it and restore the allowance before rebuilding. Oversized
compressed results continue through the original exact computation path.

Restoration validates the record, bounds decompression by the construction-time
size, rejects truncated/trailing bytes, checks decoded bytes and checks the
restored geometry. It does not reuse a previous acceptance verdict. Every
mandatory clearance and pin-separation predicate still runs against its normal
current-scene inputs. Corruption fails and closes the session; it is not hidden
by rebuilding and reporting success.

EWKB retains holes, islands, dimensions and SRID. WKB does not encode a GEOS
fixed-precision model, so nonzero-precision results deliberately retain the
original computation path. No precision conversion is attempted.

This can generalize to other expensive immutable constructions: retain a
hash-bound lossless representation when a native-object memo cannot hold the
result. The owning stage must still bind every semantic dependency. This slice
uses it only for T02 predecessor construction; no other stage is changed.
Cross-process sharing remains outside this implementation.

## Timings and parity

Both arms use the same accepted saved T04 scene (17,849 objects), shared T02
preparation and three serial worker-thread tasks. Each task reads/hashes all
operands, obtains complete neighbor records, queries five target neighborhoods,
and assembles the complete predecessor union. The reference arm uses the exact
`cef312f` native-memo-only union wrapper. The candidate enables packed reuse.
No rectangle growth search runs in this timing.

| Scope | Previous shared preparation | Packed predecessor reuse |
|---|---:|---:|
| Three-task wall time | 48.396 s | 40.011 s |
| Three-task CPU time | 48.347 s | 39.964 s |
| First-task wall | 27.547 s | 27.694 s |
| Second-task wall | 10.354 s | 6.169 s |
| Third-task wall | 10.474 s | 6.142 s |
| Exact union builds | 3 | 1 |
| Packed restorations | 0 | 2 |

This saves another **17.33% wall time** over the already shared context, and
about **40.9%** across the two subsequent tasks. The first task pays the small
compression cost. These are bounded preparation measurements, not a claimed
whole-board T02 or U05 speedup. The prior 76.683-second fresh-preparation result
is retained separately and was not rerun in this comparison.

All six task results have exact canonical parity with the saved neighbor plan,
identical ordered neighborhood answers and identical full copper WKB hashes.
All 30 neighbor groups, 99 slots and 70 entry walls are included. There is one
neighbor-record build, one spatial-index build and one union build in the
candidate arm. No approximation, check removal or source fixture modification.

## Verification and evidence

Thirteen focused tests cover the previous shared preparation controls plus:
lossless holes/islands/SRID, fixed-precision fallback, corrupt compressed bytes
and metadata, changed operands, shared-budget pressure, oversize fallback, and
complete clearance/pin report parity after restoring a complex predecessor.
Both valid-growth and deliberate invalid-growth verdicts remain identical.

The two small `rectangle_terminal` and `ordered_polarity` synthetic routes retain
both U05 passes and all 47 operations each, including actual Gerber export and
reparse. Their receipts and final qualification status are in the evidence
folder, not inferred from the saved-data preparation comparison.

Evidence: `out/lacie_work/t02_predecessor_reuse.7dkNooHP/` on the source Mac.
`PROFILE.json` identifies the union cost and representation sizes;
`BENCHMARK.json` contains all six signatures, timings and cache statistics;
`UNIT_final.log` records the thirteen focused tests. `FINAL_VALIDATION.json`
records synthetic results and source hashes. The exact executed scripts remain
beside the receipts. Existing failures and `.DS_Store` custody findings remain
preserved and unwaived.

Use the project-local Python and LaCie workspace guard. To reproduce only the
bounded saved-data comparison in a new output directory:

```sh
PYTHONPATH=. python -B tests/profile_t02_preparation.py --baseline shared \
  --saved-job "$GERBER_U05_WORKSPACE/operator_routes/gerber_u05_incremental_legacy/20261112T060513Z-7885ede64b5d4b92bf8b50f543a6f41e/legacy" \
  --output "$GERBER_U05_WORKSPACE/t02_packed_predecessor_comparison_new"
```

The profiler's `cold` JSON arm means the selected reference implementation;
with `--baseline shared`, both arms have shared preparation. Omitting that flag
retains the original fresh-per-task comparison. Neither mode runs growth search.
