"""Check the viewer CLI with saved suite and timeout evidence."""
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as xml
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SVG = "{http://www.w3.org/2000/svg}"
HALTS = {
    "no_round_pads": "NO_SOURCE_LANDS",
    "missing_eof": "missing mandatory M02 EOF marker",
    "clear_clipped_trace": "CLEAR_CLIPPED_TRACE_NEEDS_SEPARATE_FAMILY",
}


class Links(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.targets = []
        self.feed(page.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("href", "src"):
            target = attrs.get(key)
            if target and not target.startswith("#"):
                resolved = (self.page.parent / unquote(target)).resolve()
                assert resolved.is_file(), (self.page, resolved)
                self.targets.append(resolved)


def inventory(path):
    return {file.relative_to(path): (file.stat().st_size, file.stat().st_mtime_ns)
            for file in path.rglob("*") if file.is_file()}


def build(source, output, *flags):
    result = subprocess.run(
        [str(ROOT / "u05-view"), str(source), "--output", str(output), *flags],
        env={**os.environ, "U05_PYTHON": sys.executable},
        capture_output=True, text=True, check=True,
    )
    assert Path(result.stdout.strip()) == output / "index.html"
    return Path(result.stdout.strip())


def verify_svg(path):
    tree = xml.parse(path)
    assert tree.getroot().tag == SVG + "svg"
    paths = {node.attrib["id"]: node.attrib["d"] for node in tree.iter(SVG + "path")}
    assert paths["before"] and paths["after"]
    return paths


def check(suite, timeout, workspace):
    before = inventory(suite), inventory(timeout)
    output = Path(tempfile.mkdtemp(prefix="u05_view_check.", dir=workspace))
    index = build(suite, output / "suite")
    targets = Links(index).targets
    pages = [path for path in targets if path.name == "index.html"]
    case_names = {path.name for path in suite.iterdir() if path.is_dir()}
    assert len(pages) == len(case_names)
    if (suite / "SUITE.json").is_file():
        assert suite / "SUITE.json" in targets
        assert "Trial verdict" in index.read_text()
    successes = []
    for page in pages:
        links = Links(page).targets
        html = page.read_text()
        for section in ("Source assembly", "First pass", "Local reference", "Connected pass", "Controls and delivery"):
            assert section in html
        for target in set(links):
            if target.suffix == ".svg":
                verify_svg(target)
        case = page.parent.name.split("-", 1)[0]
        if case in HALTS:
            assert HALTS[case] in html
            assert "Delivered Gerber" not in html and not (page.parent / "legacy-t01.svg").exists()
        else:
            assert "U05_EXPORT_REPARSE_CONTROLS_RENDER_PASSED" in html
            assert "Delivered Gerber" in html and "Delivered 4× render" in html
            assert "Corruption outcomes" in html
            for phase in ("legacy", "connected"):
                for stage in ("t01", "t03", "t04", "t02", "t05", "export"):
                    assert (page.parent / f"{phase}-{stage}.svg").is_file(), (page, phase, stage)
            for name in ("source-assembly.svg", "reference-export.svg"):
                assert (page.parent / name).is_file()
            successes.append(page)
    expected_halts = len(case_names.intersection(HALTS))
    assert len(successes) == len(case_names) - expected_halts
    junction = next(page.parent for page in successes if page.parent.name.startswith("round_and_junction-"))
    for stage in ("t01", "t04", "t02", "t05"):
        assert verify_svg(junction / f"connected-{stage}.svg")["added"]
    assert not verify_svg(junction / "connected-t03.svg")["added"]

    finished_job, = (suite / "ordered_polarity/work/operator_routes/gerber_u05").glob("*/STATUS.current.json")
    links_only = build(finished_job, output / "links-only", "--links-only")
    assert not list(links_only.parent.glob("*.svg"))
    assert any(path.name == "corrected_growth.png" for path in Links(links_only).targets)
    timeout_page = build(timeout, output / "timeout")
    assert "TRIAL_TIMED_OUT" in timeout_page.read_text() and "STOPPED_TIMEOUT" in timeout_page.read_text()
    assert any(path.name == "TRIAL_TIMEOUT.json" for path in Links(timeout_page).targets)
    partial_job = output / "partial-job"
    (partial_job / "legacy").mkdir(parents=True)
    (partial_job / "STATUS.current.json").write_bytes((timeout / "STATUS.current.json").read_bytes())
    (partial_job / "legacy/t03.json").write_text('{"output_scene_ref":')
    partial_page = build(partial_job, output / "partial")
    assert "Unreadable saved records" in partial_page.read_text()
    assert any(path.name == "t03.json" for path in Links(partial_page).targets)
    assert before == (inventory(suite), inventory(timeout))
    print(json.dumps({"status": "PASS", "completed": len(successes), "expected_halts": expected_halts,
                      "timeout_reports": 1, "links_only_reports": 1, "index": str(index)}))


if __name__ == "__main__":
    check(*(Path(value).resolve(strict=True) for value in sys.argv[1:]))
