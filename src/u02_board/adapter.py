"""Finite copper checks for source trace and port interactions."""
from shapely import to_wkb
from src.stage_abi.store import digest


def pair_check(core, candidate, trace, port, policy):
    addition = candidate.difference(core)
    band = trace.buffer(policy['hard_gap_mm'], quad_segs=policy['quad_segs'])
    if port is not None:
        band = band.difference(port)
    intrusion = addition.intersection(band).area
    outside_contact = addition.intersection(trace)
    if port is not None:
        outside_contact = outside_contact.difference(port)
    # Match the retained T01 finite-area policy, not a new distance tolerance.
    passed = intrusion <= policy['area_epsilon_mm2']
    return dict(passed=passed, forbidden_intrusion_mm2=intrusion,
                new_contact_outside_port_mm2=outside_contact.area,
                original_contact_preserved=core.intersection(trace).difference(candidate).area <= policy['area_epsilon_mm2'],
                port_sha256=None if port is None else digest(to_wkb(port, byte_order=1)))
