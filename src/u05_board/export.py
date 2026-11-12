"""U05 Gerber support contours and physical spindle checks."""
from shapely.ops import unary_union
from src.pcb_data_abi.geometry import CIRCLE_TOLERANCE_MM, POLYGON_TOLERANCE_MM
from src.junction_spindle_stage import CONTRACT
from src.junction_spindle_blend import check_spindle

NATIVE_OWNER_OVERLAP_MM = 2 * max(CIRCLE_TOLERANCE_MM, POLYGON_TOLERANCE_MM)


def export_region(addition,owner,window,*,support_from_owner=False):
    # Duplicate only existing owner copper next to the addition. The physical
    # union is unchanged; the overlap prevents native clipping of razor tips.
    target=owner.union(addition)
    if support_from_owner:
        support=owner.intersection(addition.buffer(NATIVE_OWNER_OVERLAP_MM,quad_segs=64)).intersection(window).difference(addition)
        region=addition.union(support)
    else:
        region=target.intersection(addition.buffer(NATIVE_OWNER_OVERLAP_MM,quad_segs=64)).intersection(window)
        support=region.difference(addition)
    if support.difference(owner).area>CONTRACT.area_epsilon_mm2 or addition.difference(region).area>CONTRACT.area_epsilon_mm2 or owner.union(region).symmetric_difference(target).area>CONTRACT.area_epsilon_mm2 or region.difference(window).area>CONTRACT.area_epsilon_mm2:raise ValueError('U05_NATIVE_SUPPORT_CHANGES_QUALIFIED_COPPER')
    return region,support


def actual_spindle_check(owner,regions,addition,window,foreign):
    # Test the physical plotted union directly. Re-subtracting and re-adding
    # owner copper can manufacture disconnected ULP-sized GEOS slivers.
    candidate=owner.union(unary_union(regions))
    return check_spindle(owner,candidate,addition,window,foreign,gap=CONTRACT.hard_gap_mm)
