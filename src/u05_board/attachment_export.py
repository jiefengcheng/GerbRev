"""Positive attachment obligations measured on the Gerber export."""
from shapely.geometry import Polygon, box
from shapely.errors import GEOSException
from shapely.ops import unary_union
from src.junction_spindle_stage import CONTRACT

FILE_UNCERTAINTY_MM = .000002


def obligation_check(required,before,regions,*,already=False):
    """Require the whole approved extent, not merely some nearby new copper."""
    physical=unary_union(regions).difference(before) if regions else Polygon()
    # No copper farther than the buffer radius can cover the obligation.
    # A two-radius halo keeps every clipping edge outside that influence.
    # This checks the COMPLETE required extent, not sampled points or a crop
    # substituted for an obligation. The unchanged full operation remains the
    # fallback for any local rejection or unsupported local geometry.
    if required.is_empty:local=Polygon()
    else:
        a,b,c,d=required.bounds;halo=2*FILE_UNCERTAINTY_MM
        try:local=before.intersection(box(a-halo,b-halo,c+halo,d+halo))
        except GEOSException:local=before
    present=local if already else local.union(unary_union(regions))
    missing=required.difference(present.buffer(FILE_UNCERTAINTY_MM,quad_segs=64))
    if missing.area>CONTRACT.area_epsilon_mm2:
        present=before if already else before.union(unary_union(regions))
        missing=required.difference(present.buffer(FILE_UNCERTAINTY_MM,quad_segs=64))
    if missing.area>CONTRACT.area_epsilon_mm2:raise ValueError('U05_ACTUAL_ATTACHMENT_EXTENT_MISSING')
    effective=physical.intersection(required.buffer(FILE_UNCERTAINTY_MM,quad_segs=64)).area
    if not already and (required.area<=CONTRACT.minimum_visible_addition_mm2 or effective<=CONTRACT.minimum_visible_addition_mm2):raise ValueError('U05_ACTUAL_ATTACHMENT_NO_EFFECT')
    return dict(passed=True,required_area_mm2=required.area,missing_beyond_file_uncertainty_mm2=missing.area,effective_actual_addition_mm2=effective,file_uncertainty_mm=FILE_UNCERTAINTY_MM)
