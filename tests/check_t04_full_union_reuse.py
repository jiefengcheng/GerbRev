"""Full-scene union reuse preserves complete reports and keeps the guard."""
from unittest.mock import patch

from shapely.geometry import box
from src import prepared_width_scene as width


original = {
    "a": box(0, 0, .10, .04),
    "b": box(.136, .076, .236, .116),
}
baseline = [dict(id=sid, original=g, candidate=g, verified_original_width_mm=.10)
            for sid, g in original.items()]
fixed = [dict(id="fixed", geometry=box(-.06, .015, -.0426, .025), trace_width_mm=.10)]
scenes = [[dict(row, candidate=row["original"].buffer(growth, quad_segs=32))
           for row in baseline] for growth in (.001, .0025, .020)]


def checks(budget):
    scene = width.PreparedWidthScene(baseline, fixed, original_union_cache_bytes=budget)
    with patch.object(width, "unary_union", wraps=width.unary_union) as unions:
        reports = [scene.check(rows, materialize_scene=True) for rows in scenes]
    assert scene.original_neighbor_union_weight <= budget
    return reports, unions.call_count


reference, baseline_unions = checks(0)
candidate, cached_unions = checks(1024*1024)
assert reference == candidate
assert [r["passed"] for r in candidate] == [True, True, False]
assert cached_unions < baseline_unions
# A cache too small to fit even one entry still executes the full exact path.
assert checks(1) == (reference, baseline_unions)
print(f"PASS: exact final reports, clearance rejection retained, {baseline_unions} -> {cached_unions} unions")
