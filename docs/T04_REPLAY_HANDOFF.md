# T04 replay optimization and agent handoff

## Results through 3,600 proposals

| Measurement | Before | Pair reuse |
|---|---:|---:|
| Five saved proposal checks | 151.11 s | 27.72 s |
| Fresh setup, checkpoint restore, and five proposals | 291.01 s | 159.26 s |
| Fourth proposal | 112.54 s | 5.27 s |
| Source copper unions in the fourth proposal | 820 | 12 |

The fourth proposal carried 1,166 of 1,193 pair witnesses. All five verdicts matched. Twelve distant gap values differed by at most 8.89e-15 mm. The larger replay reached 3,600 of 7,069 proposals with 1,485 accepted and all verdicts matching so far. Its report hashes differed and some measured gap differences exceeded the small sample's comparison bound. Final nominal and envelope checks, output comparison, and the full witness audit are pending.

The running harness writes each full report twice. A two-second sample found the worker in the write syscall in 127 of 179 observations. The isolated replacement writes a gzip artifact once per logical report hash and keeps only references in the proposal ledger. The checkpoint fixture matched uninterrupted decisions and report references after restart in a fresh process. It also verified deduplication and rejection of a truncated report. Speedup from the new evidence path and restart cost on a full saved board are unmeasured.

The replay uses the saved predecessor and saved proposal ledger. Protected pin, nominal, envelope, and final output checks still govern the result. Preserve prior failure evidence and the existing .DS_Store custody finding.

## Structures and algorithms

- **Stable source catalogue and geometry map.** Key each route or feature by source ID. Keep the original geometry and ports available, along with accepted geometry, its immutable digest, and the proposed geometry. Changes are measured against the accepted predecessor. Source membership supplies identity and scope.
- **Spatial query and reverse dependencies.** An STRtree indexes conservative envelopes. Filter hits by actual bounds and include both previous and proposed extents when finding affected checks. The reverse map from dependency IDs to consumer IDs helps invalidate cached work. The current complete spatial query establishes coverage even after cache eviction.
- **Accepted pair witnesses.** Index each accepted route's pair records by neighbor ID. A witness records the neighbor, the port hash, the gap or empty-copper result, and the verdict. Reuse requires unchanged subject and neighbor geometry under the same source and policy binding, a passing witness, and a distance outside the construction guard band when a distance is present. A changed pair, new neighbor, or near-boundary result takes the existing exact path. Build exposed copper lazily for the first pair that needs it.
- **Proposal transaction.** Evaluate against accepted state. Carry provisional geometry and proofs until all proposal gates pass. Publish through accept and keep rejected proposals as evidence. Run the full nominal and envelope checks at the end, including after a terminal checkpoint reload.
- **Evidence and restart.** Hash canonical report bytes before encoding, publish the gzip file atomically, and return the logical reference. A checkpoint stores the next ledger cursor, accepted rung and geometry maps, passing witnesses and chain hash, and ordered proposal references. Bind it to saved inputs, settings, policy, implementation, and geometry runtime. On restart, verify referenced bytes and decisions against the saved prefix and rebuild accepted state before processing the next row. A checkpoint carries accepted state only. Transient caches can warm again, which can affect timing and numerical report details. The live worker predates this checkpoint path and its recorded proposal count is progress evidence.

## Extending the pattern

| Step | Useful units and dependencies | Checks that retain authority |
|---|---|---|
| T01 | Pad candidates keyed by source IDs, component membership and local clearance windows | Circle eligibility, surrounding geometry and accepted growth limits |
| T02 | Pad and pocket proposals keyed by stable source groups, affected neighbors and protected-core geometry | Accepted T04 copper, shared gap rules and permitted area budgets |
| T03 | Route and junction edits keyed by source segments, previous and proposed bounds and affected endpoints | Route continuity, junction and exact clearance checks |
| T05 | Admitted attachment ports keyed by contacting features, protected branches and patch bounds | Dark primitive admission, connectivity, pin separation and final fidelity |

For each step, start by recording candidate, dependency and policy hashes alongside the exact checker result. Compare the cached path with that step's full checker on saved proposals and include altered operands, boundary values, missing evidence, rejected trials and restarts. Keep candidate generation, exact checks, evidence writes, checkpoint reload and final output verification as separate timing rows. Measure wall and CPU time, checkpoint bytes and replayed work after restart.

## Agent loop

Read the [machine-readable replay ABI](../contracts/t04/saved_replay_abi.json) before running the profile. Derive the next action from a validated receipt and the run lock. For a new isolated attempt run `python -B profile_saved_t04.py EVIDENCE SCRATCH`. Continue a stopped attempt with the same inputs and scratch plus `--resume`. Use `--limit` for bounded diagnostics and increase the limit when continuing. Check the artifact hash through ReplayEvidence.get before interpreting a report.

After all proposals and final checks, compare the output scene and final reports with the sealed baseline. Count verdict changes, witness coverage, numeric gap differences, and guard crossings independently of report-hash changes. Use the retained CPU and wall timing categories to rank bottlenecks. A proposal count or bounded pass provides evidence for that scope only.

The diagnostic ABI describes this CLI and its files. It is a template for other stage adapters and has no deployed service endpoint.
