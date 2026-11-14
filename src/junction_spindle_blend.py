"""Additive land-sized rolling-disc blends of source-qualified neck owners.

Unlike a trace-width-capped taper, closing fills concave circle/trace shoulders.
It never changes source operands or invents an attachment between separate owners.
"""
from src.clearance_policy import HARD_GAP_MM, CONSTRUCTION_GAP_MM, CONTACT_BUFFER_MM, LEGACY_CONSTRUCTION_MM, BARRIER_GAP_MM
import math
from shapely.geometry import box


def spindle_addition(owner, radius, window, *, geometry=None):
    """Compute the exact addition, sharing the closing across route windows."""
    if geometry is None:
        from src.stage_abi.preparation import geometry_memo
        geometry=geometry_memo()
    if not math.isfinite(radius) or radius<=0:raise ValueError('POSITIVE_BLEND_RADIUS_REQUIRED')
    if owner.is_empty or not owner.is_valid or owner.geom_type!='Polygon':
        raise ValueError('ONE_CONNECTED_QUALIFIED_OWNER_REQUIRED')
    # Keep exact predecessor contributions. Only the closing's added copper is
    # clipped to the declared local window; never erode the original owner.
    def unwindowed_addition():
        closed=owner.buffer(radius,quad_segs=64).buffer(-radius,quad_segs=64)
        return closed.difference(owner)

    if geometry is None:
        return unwindowed_addition().intersection(window)
    addition=geometry.construct('spindle-unwindowed-addition', [owner], (radius,64),
                                unwindowed_addition)
    return geometry.intersection(addition,window)


def spindle_blend(owner, radius, window, *, geometry=None):
    if geometry is None:
        from src.stage_abi.preparation import geometry_memo
        geometry=geometry_memo()
    addition=spindle_addition(owner,radius,window,geometry=geometry)
    candidate=owner.union(addition) if geometry is None else geometry.union(owner,addition)
    return candidate,addition


def check_spindle(owner, candidate, addition, window, foreign, gap=CONSTRUCTION_GAP_MM, *, geometry=None, quick_disjoint=False):
    if geometry is None:
        from src.stage_abi.preparation import geometry_memo
        geometry=geometry_memo()
    failures=[];pairs=[]
    difference=(lambda a,b:a.difference(b)) if geometry is None else geometry.difference
    union=(lambda a,b:a.union(b)) if geometry is None else geometry.union
    symmetric_difference=(lambda a,b:a.symmetric_difference(b)) if geometry is None else geometry.symmetric_difference
    if not candidate.is_valid or candidate.geom_type!='Polygon':failures.append('DISCONNECTED_OR_INVALID_CANDIDATE')
    if difference(owner,candidate).area>1e-12:failures.append('OWNER_REMOVED')
    if difference(addition,window).area>1e-12:failures.append('OUTSIDE_WINDOW')
    if symmetric_difference(candidate,union(owner,addition)).area>1e-12:failures.append('DELTA_MISMATCH')
    owner_bounds=owner.bounds if quick_disjoint else None
    for sid,g in foreign:
        disjoint=False
        if quick_disjoint:
            bounds=g.bounds
            disjoint=(owner_bounds[2]<bounds[0] or bounds[2]<owner_bounds[0]
                      or owner_bounds[3]<bounds[1] or bounds[3]<owner_bounds[1])
        covered=False if disjoint else (g.difference(owner).is_empty if geometry is None else geometry.difference_empty(g,owner))
        if covered:
            pairs.append(dict(source_id=sid,disposition='EXACTLY_COVERED_BY_QUALIFIED_OWNER'));continue
        distance=None if addition.is_empty else addition.distance(g)
        passed=distance is None or distance+1e-12>=gap
        pairs.append(dict(source_id=sid,gap_mm=distance,passed=passed))
        if not passed:failures.append('FOREIGN_CLEARANCE:'+sid)
    return dict(passed=not failures,failures=failures,pairs=pairs)
