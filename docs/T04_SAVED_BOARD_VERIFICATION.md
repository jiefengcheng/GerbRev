# T04 saved-board verification for ac1ef1d

The isolated run passed the complete nominal and envelope checks at commit `ac1ef1da81b1aedc77b9379e59c7ef94a89f0a1b`. It restored pass four, validated the sealed proposal ledger, ran both final scene checks, and assembled the output scene. It performed zero fresh proposal geometry evaluations.

The restored pass-four report, both canonical final reports, and the assembled output scene matched the saved run byte-for-byte. Both final reports cover 3,384 traces. All 17,849 output geometry references matched.

| Artifact | SHA-256 shared by saved and candidate output |
|---|---|
| Nominal report | `5a999f315aa25ee15890b340bbe7d64a004d4c52463e71c2f4f33d323cefcaa0` |
| Envelope report | `827c9482980d100406cec9dc6720872b9a53ad741fde69c9402480fa74224089` |
| Output scene | `d1f47c69149ec533804d1f3b6515f4707fb4cea2e902bea5667465cf0159dc94` |

| Measured phase | Wall (s) | CPU (s) |
|---|---:|---:|
| Initialize saved T03 | 106.40 | 101.47 |
| Restore and verify pass four | 960.02 | 958.87 |
| Validate the complete recorded ledger | 282.02 | 236.57 |
| Transfer restored visibility entries | 0.00134 | 0.00134 |
| Nominal scene check | 512.47 | 511.94 |
| Envelope scene check | 397.31 | 396.96 |
| **Combined nominal and envelope scene checks** | **909.78** | **908.90** |
| Write output scene | 8.98 | 2.66 |
| **Entire verification run** | **2,344.41** | **2,280.98** |

The earlier saved replay profile measured the same two scene-check calls at 1,414.00 s wall and 1,412.20 s CPU. The candidate reduced the measured wall time of those calls by 504.22 s (35.7%). This comparison covers the two scene checks. The total verification time also includes setup, pass-four restoration, ledger validation, output assembly, and report comparison.

The verifier carries forward exact source-visibility geometry for unchanged neighbors. The original source binding and current geometry digest govern reuse, and the complete final checks run on the selected geometry. The recorded-ledger run verifies the saved decisions and their witnesses. A fresh 7,069-proposal replay is on hold.
