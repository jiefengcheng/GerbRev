"""Check exact final report parity when source visibility carries forward."""
from unittest.mock import patch

from shapely.geometry import box
from src import prepared_width_scene as width


cores = {"a": box(0, 0, .10, .04), "b": box(.136, .076, .236, .116)}
baseline = [dict(id=sid, original=g, candidate=g, verified_original_width_mm=.10)
            for sid, g in cores.items()]
fixed = [dict(id="fixed", geometry=box(-.06, .015, -.0426, .025), trace_width_mm=.10)]


def rows(growth):
    return [dict(row, candidate=row["original"].buffer(growth[row["id"]], quad_segs=32))
            for row in baseline]


restored = width.PreparedWidthScene(baseline, fixed)
assert restored.check(rows({"a": .002, "b": .002}), materialize_scene=True)["passed"]
inputs = [rows({"a": .002, "b": .002}), rows({"a": .008, "b": .004})]


def checks(carry):
    final = width.PreparedWidthScene(baseline, fixed)
    if carry:
        final.inherit_source_visibility(restored)
    with patch.object(width, "unary_union", wraps=width.unary_union) as unions:
        reports = [final.check(scene, materialize_scene=True) for scene in inputs]
    return reports, unions.call_count


reference, cold_unions = checks(False)
candidate, warm_unions = checks(True)
assert reference == candidate
assert [r["passed"] for r in candidate] == [True, False]
assert warm_unions < cold_unions
other = [dict(fixed[0], geometry=box(-.07, .015, -.0426, .025))]
try:
    width.PreparedWidthScene(baseline, other).inherit_source_visibility(restored)
except ValueError as error:
    assert str(error) == "WIDTH_VISIBILITY_SOURCE_BINDING_CHANGED"
else:
    raise AssertionError("Different original source accepted")
print(f"PASS: exact final reports and rejection, {cold_unions} -> {warm_unions} unions")
