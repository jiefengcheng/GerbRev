"""Find all source-contact proofs for the owner-based native land checker."""
from shapely import STRtree


def source_contact_ports(checker, lands, original_shapes, make_port):
    ids = checker.ids
    tree = STRtree([original_shapes[sid] for sid in ids])
    proofs = []
    for land in lands:
        sid = land['id']
        original = original_shapes[sid]
        for index in sorted(map(int, tree.query(original))):
            other = ids[index]
            if other == sid:
                continue
            neighbor = original_shapes[other]
            overlap = original.intersection(neighbor)
            if overlap.is_empty:
                continue
            width = max(checker.widths[sid], checker.widths[other]) + checker.contract.original_port_buffer_gap_mm
            port, proof = make_port(overlap, width, True)
            checker.ports[(sid, other)] = (port, True, original.distance(neighbor))
            proofs.append(dict(source_id=sid, neighbor_id=other, **proof))
    return proofs
