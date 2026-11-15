"""A changed neighbor and a boundary gap still require fresh clearance checks."""
from unittest.mock import patch

from shapely.geometry import box

from src.t04_incremental import IncrementalRoutes
from src.t04_settings import capture


source = {
    'a': box(0, 0, .10, .04),
    'b': box(.136, .076, .236, .116),
}
baseline = [
    dict(id=sid, original=g, candidate=g, verified_original_width_mm=.10)
    for sid, g in source.items()
]


def run(reuse):
    fixed = [dict(id='distant', geometry=box(-.136, .076, -.036, .116), trace_width_mm=.10)]
    checker = IncrementalRoutes(
        baseline, fixed,
        lambda sid, factor, envelope: source[sid].buffer((factor-1)*.05, quad_segs=32),
        capture(), dict.fromkeys(source, .10),
    )
    checker.fallback.reuse_accepted_pairs = reuse
    reports = []
    for sid, factor in [('a', 1.05), ('b', 1.05), ('b', 1.4)]:
        report = checker.evaluate(sid, factor)
        reports.append(report)
        if report['passed']:
            checker.accept(sid, factor)
    assert [report['passed'] for report in reports] == [True, True, False]
    assert reports[-1]['failures'][0]['reason'] == 'NEW_EXPOSED_COPPER_BELOW_CONSTRUCTION_GUARD'
    return reports, checker.fallback.accepted_pair_reuses


reference, _ = run(False)
candidate, reuses = run(True)
assert reference == candidate and reuses > 0

fixed = [dict(id='boundary', geometry=box(-.06, .015, -.0426, .025), trace_width_mm=.10)]
checker = IncrementalRoutes(
    baseline, fixed,
    lambda sid, factor, envelope: source[sid].buffer((factor-1)*.05, quad_segs=32),
    capture(), dict.fromkeys(source, .10),
)
assert checker.evaluate('a', 1.05)['passed']
checker.accept('a', 1.05)
with patch.object(checker.fallback, 'exact_distance', wraps=checker.fallback.exact_distance) as distance:
    assert checker.evaluate('b', 1.05)['passed']
    assert any(call.args[:2] == ('a', 'boundary') for call in distance.call_args_list)
print('PASS: unchanged pair reused, changed neighbor rejected, boundary pair rechecked')
