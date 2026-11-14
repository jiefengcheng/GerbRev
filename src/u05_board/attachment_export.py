"""Positive attachment obligations measured on the Gerber export."""
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.errors import GEOSException
from shapely.ops import unary_union
from shapely.strtree import STRtree
from src.junction_spindle_stage import CONTRACT

FILE_UNCERTAINTY_MM = .000002

class PreparedAttachmentCopper:
    """Index complete predecessor components; retain the original for fallback."""
    def __init__(self, before):
        self.before=before
        if before.is_valid and before.geom_type in ('Polygon','MultiPolygon'):
            self.parts=[before] if before.geom_type=='Polygon' else list(before.geoms)
            self.tree=STRtree(self.parts)
        else:
            self.parts=None;self.tree=None

    def nearby(self, shape):
        if self.tree is None:return self.before
        if shape.is_empty:return Polygon()
        parts=[self.parts[int(i)] for i in sorted(self.tree.query(shape))]
        if not parts:return Polygon()
        return parts[0] if len(parts)==1 else MultiPolygon(parts)


def obligation_check(required,before,regions,*,already=False,prepared=None):
    """Require the whole approved extent, not merely some nearby new copper."""
    if prepared is not None and prepared.before is not before:raise ValueError('ATTACHMENT_PREDECESSOR_INDEX_CHANGED')
    material=unary_union(regions) if regions else Polygon()
    physical=material.difference(prepared.nearby(material) if prepared is not None else before) if regions else Polygon()
    # No copper farther than the buffer radius can cover the obligation.
    # A two-radius halo keeps every clipping edge outside that influence.
    # This checks the COMPLETE required extent, not sampled points or a crop
    # substituted for an obligation. The unchanged full operation remains the
    # fallback for any local rejection or unsupported local geometry.
    if required.is_empty:local=Polygon()
    else:
        a,b,c,d=required.bounds;halo=2*FILE_UNCERTAINTY_MM
        window=box(a-halo,b-halo,c+halo,d+halo)
        try:local=(prepared.nearby(window) if prepared is not None else before).intersection(window)
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
