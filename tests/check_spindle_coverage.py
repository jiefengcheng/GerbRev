"""Check coverage and distance results for overlapping and distant copper."""
from shapely.geometry import GeometryCollection, box
from src.junction_spindle_blend import check_spindle


class Geometry:
    def difference(self, a, b): return a.difference(b)
    def difference_empty(self, a, b): return a.difference(b).is_empty
    def union(self, a, b): return a.union(b)
    def symmetric_difference(self, a, b): return a.symmetric_difference(b)


def check():
    owner = box(0, 0, 1, 1)
    addition = box(1, 0.25, 1.1, 0.75)
    candidate = owner.union(addition)
    foreign = [
        ("inside", box(.1, .1, .2, .2)),
        ("touching", box(1, .2, 1.2, .3)),
        ("distant", box(4, 4, 5, 5)),
        ("empty", GeometryCollection()),
    ]
    normal = check_spindle(owner, candidate, addition, box(0, 0, 2, 2), foreign)
    quick = check_spindle(owner, candidate, addition, box(0, 0, 2, 2), foreign, quick_disjoint=True)
    memo = check_spindle(owner, candidate, addition, box(0, 0, 2, 2), foreign, geometry=Geometry(), quick_disjoint=True)
    assert normal == quick == memo
    results = {row["source_id"]: row for row in normal["pairs"]}
    assert results["inside"]["disposition"] == "EXACTLY_COVERED_BY_QUALIFIED_OWNER"
    assert results["empty"]["disposition"] == "EXACTLY_COVERED_BY_QUALIFIED_OWNER"
    assert results["touching"]["passed"] is False and results["touching"]["gap_mm"] == 0
    assert results["distant"]["passed"] is True and results["distant"]["gap_mm"] > .04
    print("PASS: coverage and clearance results match with and without geometry memoization")


if __name__ == "__main__":
    check()
