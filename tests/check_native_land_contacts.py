"""Compare indexed source-contact certificates with the exhaustive construction."""
from types import SimpleNamespace
from shapely.geometry import box
from src.gerber_u05.legacy_export import original_contact_port
from src.gerber_u05.native_land_contacts import source_contact_ports
from src.trace_width_clearance import TraceWidthContract


def check():
    shapes = {
        "land": box(0, 0, 1, 1),
        "overlap": box(.8, .2, 1.2, .8),
        "touch": box(1, .8, 2, 1),
        "far": box(5, 5, 6, 6),
    }
    checker = SimpleNamespace(ids=sorted(shapes), widths={sid: 0. for sid in shapes},
                              contract=TraceWidthContract(), ports={})
    lands = [{"id": "land"}]
    expected = []
    for sid in checker.ids:
        if sid == "land":
            continue
        overlap = shapes["land"].intersection(shapes[sid])
        _, proof = original_contact_port(overlap, checker.contract.original_port_buffer_gap_mm,
                                         not overlap.is_empty)
        if proof is not None:
            expected.append(dict(source_id="land", neighbor_id=sid, **proof))
    actual = source_contact_ports(checker, lands, shapes, original_contact_port)
    assert actual == expected
    assert set(checker.ports) == {("land", "overlap"), ("land", "touch")}
    print("PASS: indexed proofs match exhaustive overlapping and touching source contacts")


if __name__ == "__main__":
    check()
