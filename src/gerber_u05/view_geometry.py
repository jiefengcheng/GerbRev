"""Read saved copper and draw common-coordinate SVG comparisons."""
import hashlib
import json
from pathlib import Path

from shapely.affinity import scale
from shapely.ops import unary_union

from src.component_voids import surface_parts
from src.stage_abi.scene import composed, geometry, validate_scene


class EvidenceStore:
    """Read only content-addressed artifacts without opening a writable store."""

    def __init__(self, run):
        self.artifacts = run / "runtime" / "artifacts"

    def get(self, reference, *, kind):
        digest = reference["sha256"]
        if (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
                or reference["artifact_id"] != f"{kind}:{digest}"):
            raise ValueError("Invalid artifact reference")
        artifact = self.artifacts / reference["artifact_id"]
        if artifact.is_symlink():
            raise ValueError("Linked artifact")
        data = artifact.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Artifact digest mismatch")
        return data

    def get_json(self, reference, *, kind):
        return json.loads(self.get(reference, kind=kind))


def scene_copper(run, reference):
    store = EvidenceStore(run)
    return composed(store, validate_scene(store, reference))


def gerber_copper(path, *, generated=False, sha256=None):
    from . import gerber_source_profile as source

    data = Path(path).read_bytes()
    if sha256 is not None and hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("Gerber digest mismatch")
    if generated:
        from .legacy_export import parse

        parsed = parse(data)
    else:
        parsed, _, _ = source.parse_source(data)
    copper = source.ordered((source.object_geometry(obj)[0], obj.polarity_dark) for obj in parsed.objects)
    return scale(copper, xfact=1, yfact=-1, origin=(0, 0))


def exported_copper(run, proof):
    path = run / "export" / "top.art.gbr"
    if "actual_material_image_ref" in proof:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != proof["generated_sha256"]:
                raise ValueError("Export digest mismatch")
        return geometry(EvidenceStore(run), proof["actual_material_image_ref"])
    return gerber_copper(path, generated=True, sha256=proof["generated_sha256"])


def padded(bounds):
    x0, y0, x1, y1 = bounds
    width, height = x1 - x0, y1 - y0
    pad = max(width, height, 0.01) * 0.08
    return x0 - pad, y0 - pad, width + 2 * pad, height + 2 * pad


def coordinates(shape):
    paths = []
    for polygon in surface_parts(shape):
        for ring in (polygon.exterior, *polygon.interiors):
            points = " ".join(f"{x:.9g},{y:.9g}" for x, y in list(ring.coords)[:-1])
            paths.append(f"M {points} Z")
    return " ".join(paths)


def comparison(path, before, after, viewport):
    """Save the same material at full scale and, when useful, a close-up."""
    added, removed = after.difference(before), before.difference(after)
    changed = surface_parts(unary_union((added, removed)))
    detail = padded(max(changed, key=lambda part: part.area).bounds) if changed else None
    definitions = (
        ("before", before, "#bac8ce"), ("after", after, "#bac8ce"),
        ("added", added, "#42f599"), ("removed", removed, "#ff738c"),
    )
    defs = "".join(
        f'<path id="{key}" fill="{color}" fill-rule="evenodd" d="{coordinates(shape)}"/>'
        for key, shape, color in definitions
    )
    panels = [("Entry", viewport, ("before",)), ("Result", viewport, ("after", "added", "removed"))]
    if detail:
        panels.append(("Largest change", detail, ("after", "added", "removed")))
    width = 440
    blocks = []
    for index, (label, bounds, layers) in enumerate(panels):
        viewbox = " ".join(f"{value:.9g}" for value in bounds)
        shapes = "".join(f'<use href="#{name}"/>' for name in layers)
        x = index * width + 5
        blocks.append(f'<text x="{x + 12}" y="25">{label}</text>'
                      f'<rect x="{x}" y="37" width="430" height="280" rx="8" fill="#102634"/>'
                      f'<svg x="{x}" y="37" width="430" height="280" viewBox="{viewbox}">{shapes}</svg>')
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width * len(panels)} 325" '
                    f'font-family="system-ui,sans-serif" font-size="17" fill="#dbe8ef">'
                    f'<defs>{defs}</defs>{"".join(blocks)}</svg>\n', encoding="utf-8")
    return added.area, removed.area
