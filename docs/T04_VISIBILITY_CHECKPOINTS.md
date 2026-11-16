# Exact visibility in T04 pass checkpoints

This isolated change retains the exact visible-copper operands already computed by the T04 checker. It does not replace clearance, pin-separation, affected-neighbor, accepted-witness, or final nominal/envelope checks.

## Data and reuse

Each content-addressed pass state optionally references a `t04-visibility-records` artifact. Records contain source object ID, candidate geometry SHA-256, exact WKB digest, and compressed WKB. Empty geometries and holes are preserved. The record payload is bounded to 4 MiB (including an allowance for per-record bookkeeping), with a 64 MiB decoded limit per geometry. Oversized and non-default precision operands stay on the existing calculation path.

The packet binds source geometry and ordering, source groups, widths and clearance contract through the checker binding, plus the visibility implementation and Shapely/GEOS versions. It captures the query-window mode. Restoration validates every payload before publishing any record. The checker may restore before entering incremental mode; it only consumes records after selecting the matching mode.

A lookup uses `(source_object_id, current_geometry_sha256)`. A changed neighbor misses and follows the original calculation. Unchanged neighbors can reuse their exact operand; the proposed route's remaining checks still execute. A record may have been computed for a rejected trial: it certifies only the geometry operand, never acceptance of that trial. Existing bounded in-memory geometry caches remain in front of the restored records. Older pass states without visibility records continue on the original path.

## Restart qualification

The bounded saved-data test restores the retained 3020301113B pass-four state, evaluates five saved proposals, publishes a diagnostic checkpoint using the production pass-state API, and continues seven more proposals. A fresh process loads that checkpoint and evaluates the same seven proposals. This diagnostic cursor is inside a pass; it does not claim completion or requalification of an entire ladder pass. Production checkpoints remain at completed pass boundaries.

Compare complete canonical reports, accepted proof-chain hashes and all 3,384 current route geometries. Corruption controls reject changed binding, schema and payload; a changed geometry must execute the original visibility calculation with exact WKB parity. A separate cold continuation omits only the optional visibility packet, retaining accepted geometry, witnesses and all checks.

The full 7,069-proposal replay and full-board rerun remain on hold. Historical failures, including the initial mode-binding restart failure and prior .DS_Store custody findings, remain explicit and unwaived. This change does not establish owner or manufacturing acceptance.

## Measured saved-proposal results

| Scope | Wall seconds | CPU seconds |
|---|---:|---:|
| Seven proposals after restart, without visibility packet | 50.77 | 50.67 |
| Same seven proposals after restart, with visibility packet | 40.50 | 40.38 |
| Same seven in uninterrupted worker | 36.35 | 36.30 |
| Save checkpoint after first five | 1.09 | 0.72 |
| Restore checkpoint and 78 visibility records | 0.96 | 0.96 |

The restarted proposal loop saved 10.27 s wall (20.2%) and 10.30 s CPU. Thirteen visibility lookups hit restored records. The slowest proposal, 13544, fell from 44.14 to 35.17 s wall. It remains the dominant cost in this sample.

Setup is separate: 132.33 s with records versus 133.21 s without. Total measured process wall time was 174.14 versus 185.27 s (about 6.0% shorter), including setup, reporting and comparisons; the record run additionally executed invalidation controls. This is one bounded paired measurement, not a full-board speed forecast.

All 12 capture reports match the prior baseline bytes. Both seven-proposal continuation runs match the uninterrupted reports, accepted proof hashes and all 3,384 route geometry digests. Six unit regressions and the existing changed-neighbor/boundary-clearance regression passed. Full nominal/envelope checks remain in the route and were not rerun in this slice.

The first attempt failed on a mismatch between pre-check and active query-window modes. Its failure log is preserved. The corrected restore defers reuse until mode selection matches. After timing, one further snapshot guard was added and unit-tested: records from another mode cannot be relabelled during re-saving. The measured capture used an empty restored-record set, and both timed continuation paths did not save again; their exercised behavior is unchanged. RESULT.json retains the measured source hashes; FINAL_VALIDATION.json records the final source hashes and regression results. No claim is made that the final guard was exercised by another saved-board replay.

Evidence directory:
`out/lacie_work/t04_checkpoint_records_v2.5O8NhiTL/`

- `RESULT.json`: measurements, exact comparisons, controls and measured source hashes.
- `capture.json`, `restart.json`, `cold.json`: per-proposal timings and geometry digests.
- `checkpoint-store/`, `checkpoints/`: hash-addressed checkpoint and compressed exact records.
- `measure.py`, `measure_cold.py`, `summarize.py`: bounded experiment and comparison scripts.
- `UNIT_final.log`, `PAIR_TEST.log`: six unit tests and existing clearance regression.
- Earlier failure: `out/lacie_work/t04_checkpoint_records.NefVC2hF/restart.log`.

The repository's pytest launcher was attempted but its expected interpreter was missing; pytest is also absent from the pinned benchmark environment. The focused unittest and regression scripts ran with the existing pinned Python through the workspace preparation guard, without installing dependencies.

To keep the 5 GiB reserve, older derived nominal/envelope report duplicates were losslessly compressed and verified byte-for-byte before removing their raw copies. `out/lacie_work/t04_visibility_full_checks/REPORTS_LOSSLESS_COMPACTION.json` records hashes and archive locations. No evidence was discarded.

