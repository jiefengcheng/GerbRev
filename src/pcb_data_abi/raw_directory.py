"""Convert supported raw Gerber primitives to finite geometry."""
from gerbonara import graphic_objects as go
from gerbonara.apertures import RectangleAperture
from shapely import union_all
from src.gerber_image import object_geometry


def raw_object_geometry(obj):
    if isinstance(obj,go.Line)and isinstance(obj.aperture,RectangleAperture):
        # Translating a convex rectangular aperture along a segment is exactly
        # the convex hull of its endpoint flashes, for every segment direction.
        if obj.aperture.hole_dia:raise ValueError('RAW_GERBER_LINE_APERTURE_UNSUPPORTED')
        ends=[object_geometry(go.Flash(x=x,y=y,aperture=obj.aperture,unit=obj.unit,polarity_dark=True))for x,y in[(obj.x1,obj.y1),(obj.x2,obj.y2)]]
        return union_all(ends).convex_hull
    return object_geometry(obj)
