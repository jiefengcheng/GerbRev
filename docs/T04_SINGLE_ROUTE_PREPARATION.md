# T04 single route preparation

T04 can opt in to preparing a candidate from its accepted copper and one proposed route. The existing ladder still chooses the route and rung, and the existing predicates still determine the report. The diagnostic entry point is `IncrementalRoutes(..., prepare_single_route=True)`. Production callers use the default. [Python checker ABI](../contracts/t04/single_route_preparation_agent_abi.json)

## Reusable structures

| Structure | Reuse and ownership |
|---|---|
| `CandidateTrace` and `CandidateSnapshot` | Typed row and complete ordered snapshot. T04 constructs both from the checker’s accepted state and supplies the full snapshot to the existing pin checker. |
| Accepted geometry and witnesses | Source identities, original cores and widths bind the routes. Accepted geometry and per-route content digests determine the trial’s physical operands. `evaluate` works provisionally and `accept` publishes the passing state. |
| `BoundsView.with_bounds` | Checks finite bounds from a validated candidate against the route’s maximum envelope and copies the bounds array. It reuses the ordered STRtree and gives the trial its own query memo. Geometry outside the envelope takes the existing exact index path. |
| `RouteTrial` and `ProofGraph` | Track the preceding trial’s route and digest alongside the accepted state it came from. The next call accounts for a rejected overlay being removed, a passing overlay being committed, or a different accepted state being restored. |

Full-vector callers still validate all source rows. The single-route path uses the checker-owned accepted geometry and proof map, validates the proposed row, and patches only its bounds. The accepted and trial queries both remain in the affected-neighbor test. Copying the geometry map and bounds array still scales with scene size. The optimization removes repeated Python walks and geometry-signature lookups for unchanged routes.

After a rejection, the accepted state stays available for the next proposal. After acceptance, the prepared view can become the accepted view. An unrelated restored state clears active dependency links and rebuilds its view as needed. The three-view limit and existing exact witness bindings apply throughout.

## ABI selection

| Need | Contract |
|---|---|
| A bounded in-process T04 proposal check | [T04 single route preparation](../contracts/t04/single_route_preparation_agent_abi.json) |
| The existing saved T04 continuation and report reader | [T04 saved replay](../contracts/t04/saved_replay_abi.json) |
| T02 task leases and immutable geometry preparation | [T02 preparation](../contracts/t02/preparation_agent_abi.json) |
| Design reference for future owning-stage adapters | [Immutable preparation design](../contracts/shared/immutable_preparation_agent_abi.json) |

The one-route overlay is transient. Existing report bytes, proof-chain encoding, checkpoint validation, stage order, width caps, and final native checks retain their existing contracts.

## Bounded qualification

The A/B protocol checks a six-proposal saved sample, three consecutive rejections from one accepted state, and a saved sequence containing a neighbor update. It validates the archived state before each sequence. It measures proposal checks separately from setup and commits, and compares canonical report bytes and the accepted proof-chain hash at every step.

| Workload | Baseline warmed median | Single route warmed median | Wall reduction |
|---|---:|---:|---:|
| Six saved proposals | 65.02 ms | 31.43 ms | 51.7% |
| Three consecutive rejections | 24.74 ms | 8.93 ms | 63.9% |
| Three-proposal neighbor update sequence | 32.32 ms | 16.60 ms | 48.6% |

Across seven batches per arm, all 168 checks matched their archived reports and accepted chain hashes. First-batch reductions ranged from 0.7% to 9.8%. These timings cover the selected proposal checks. Full-board runtime remains unmeasured.

The focused synthetic tests exercise accepted and rejected proposals, rollback to an earlier state, exact fallback outside the prepared envelope, and complete ladder and final-report parity. Saved board inputs and raw qualification artifacts stay in their retained workspace.
