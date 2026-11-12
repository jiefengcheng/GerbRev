"""Build an offline visual index of saved U05 evidence."""
import argparse
import json
import os
import webbrowser
from html import escape
from pathlib import Path
from urllib.parse import quote

from shapely.errors import GEOSException

from . import view_geometry as copper

STAGES = {
    "t01": "T01 · Round pads",
    "t03": "T03 · Trace retention",
    "t04": "T04 · Trace widening",
    "t02": "T02 · Rectangular pads",
    "t05": "T05 · Junction growth and remedy",
}
TERMINAL = "U05_EXPORT_REPARSE_CONTROLS_RENDER_PASSED"
GEOMETRY_ERRORS = (OSError, ValueError, KeyError, TypeError, GEOSException)
STYLE = """
:root {color-scheme:dark; font-family:Inter,system-ui,sans-serif; background:#0c1822; color:#dbe8ef}
body {max-width:1200px; margin:0 auto; padding:28px clamp(14px,4vw,48px) 64px}
h1,h2,h3 {line-height:1.2} h2 {margin-top:40px} p {line-height:1.5}
a {color:#8ecfff} a:hover {color:#d4edff} code {overflow-wrap:anywhere}
nav {display:flex; flex-wrap:wrap; gap:8px 20px; margin:20px 0}
.section {border:1px solid #2b4354; background:#132632; border-radius:12px; padding:18px; margin:12px 0}
.section h3 {margin-top:0} .status {color:#e5c487; font-weight:600; overflow-wrap:anywhere}
.good,.added {color:#42f599} .removed {color:#ff738c} .muted,figcaption {color:#acbfcc}
.gallery {display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr)); gap:12px}
figure {margin:10px 0} img {display:block; width:100%; border-radius:8px; background:#102634}
figcaption {margin-top:6px} details {margin:12px 0} summary {cursor:pointer}
.scroll {overflow-x:auto} table {width:100%; border-collapse:collapse; margin:10px 0; font-size:.9rem}
th,td {padding:7px 10px; text-align:left; border-bottom:1px solid #304654; vertical-align:top}
.files {columns:2 240px; padding-left:22px} li {overflow-wrap:anywhere; margin-bottom:5px}
pre {white-space:pre-wrap; overflow-wrap:anywhere}
"""


def read(path):
    return json.loads(path.read_bytes())


def number(value):
    return f"{value:.6g}" if isinstance(value, float) else str(value)


def table(headers, rows):
    header = "".join(f"<th scope='col'>{escape(label)}</th>" for label in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class='scroll'><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"


def page(path, title, body):
    path.write_text(
        "<!doctype html>\n<html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{STYLE}</style><body>{body}</body></html>\n",
        encoding="utf-8",
    )


def status_label(status):
    good = " good" if status in {"PASS", TERMINAL} else ""
    return f"<span class='status{good}'>{escape(status)}</span>"


class Report:
    def __init__(self, job, output, links_only):
        self.job = job
        self.output = output
        self.links_only = links_only
        self.state = read(job / "STATUS.current.json")
        self.checks = self.state.get("checks", {})
        self.viewport = None
        self.unreadable = []

    def saved(self, path):
        if not path.is_file():
            return {}
        try:
            value = read(path)
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
        except (OSError, ValueError):
            self.unreadable.append(path)
            return {}

    def href(self, path):
        return quote(os.path.relpath(path, self.output))

    def link(self, path, label=None):
        return f'<a href="{self.href(path)}">{escape(label or path.name)}</a>'

    def artifacts(self, paths, title="Evidence files"):
        files = sorted({path for path in paths if path.is_file()})
        if not files:
            return ""
        entries = "".join(f"<li>{self.link(path, str(path.relative_to(self.job)))}</li>" for path in files)
        return f"<details><summary>{title} ({len(files)})</summary><ul class='files'>{entries}</ul></details>"

    def image(self, path, title):
        return (f'<figure><a href="{self.href(path)}"><img src="{self.href(path)}" '
                f'alt="{escape(title, quote=True)}" loading="lazy"></a><figcaption>'
                f'{escape(title)}</figcaption></figure>')

    def section(self, title, body):
        return f"<article class='section'><h3>{escape(title)}</h3>{body}</article>"

    def check_rows(self, prefix=""):
        for key, entry in self.checks.items():
            if not key.startswith(prefix):
                continue
            logs = [self.job / "logs" / f"{key}{suffix}.log" for suffix in ("", ".stderr")]
            links = [self.link(path, label) for path, label in zip(logs, ("stdout", "stderr")) if path.is_file()]
            yield escape(key), status_label(entry["status"]), escape(number(entry.get("seconds", "—"))), " · ".join(links)

    def checks_table(self, prefix):
        rows = list(self.check_rows(prefix))
        if not rows:
            return "<p class='muted'>No operation recorded.</p>"
        notes = []
        for key, entry in self.checks.items():
            if key.startswith(prefix) and entry["status"] == "FAIL":
                log = self.job / "logs" / f"{key}.stderr.log"
                if log.is_file() and log.stat().st_size:
                    with log.open("rb") as stream:
                        stream.seek(max(0, log.stat().st_size - 4096))
                        lines = stream.read().decode("utf-8", errors="replace").splitlines()
                    if lines:
                        notes.append(f"<pre>{escape(lines[-1])}</pre>")
        return table(("Operation", "Recorded status", "Seconds", "Logs"), rows) + "".join(notes)

    def compare(self, name, title, before, load_after, *, source=False):
        if self.links_only or load_after is None:
            return "", None
        try:
            after = load_after()
            if self.viewport is None:
                baseline = before if before is not None else after
                if not baseline.is_empty:
                    self.viewport = copper.padded(baseline.bounds)
            if self.viewport is None or (before is None and not source):
                return "<p class='muted'>No saved predecessor geometry for comparison.</p>", after
            path = self.output / (name + ".svg")
            entry = after if before is None else before
            added, removed = copper.comparison(path, entry, after, self.viewport)
            label = f"{title} · added {added:.6g} mm² · removed {removed:.6g} mm²"
            return self.image(path, label), after
        except GEOMETRY_ERRORS as error:
            return f"<p class='muted'>Preview unavailable. {escape(str(error))}</p>", None

    def assembly(self):
        folder = self.job / "assembly"
        receipt = self.saved(folder / "RECEIPT.json")
        original_path, assembled_path = folder / "original.gbr", folder / "assembled.gbr"
        view = ""
        raw = None
        if not self.links_only and original_path.is_file():
            try:
                raw = copper.gerber_copper(original_path, sha256=receipt.get("raw_source_sha256"))
            except GEOMETRY_ERRORS as error:
                view = f"<p class='muted'>Source preview unavailable. {escape(str(error))}</p>"
        if raw is not None:
            if assembled_path.is_file():
                load = lambda: copper.gerber_copper(assembled_path, sha256=receipt.get("assembled_source_sha256"))
                view, _ = self.compare("source-assembly", "Source assembly", raw, load)
            else:
                view, _ = self.compare("source-assembly", "Saved source", None, lambda: raw, source=True)
        evidence = [self.job / "INPUT_INVENTORY.json", self.job / "RESOURCE_MANIFEST_PROOF.json",
                    *folder.glob("*.json"), *folder.glob("*.gbr"), *folder.glob("audits/*.json")]
        return self.section("Original and assembled copper",
                            view + self.checks_table("assembly_") + self.artifacts(evidence))

    def stage_summary(self, stage, record):
        values = [(escape(key.replace("_", " ")), escape(number(value)))
                  for key, value in record.get("summary", {}).items()]
        result = table(("Measure", "Saved value"), values) if values else ""
        if stage == "t01":
            decisions = record.get("decisions", [])
            columns = (("source_id", "Source"), ("added_area_mm2", "Added mm²"), ("reason", "Reason"))
        elif stage == "t03":
            decisions = record.get("records", [])
            columns = (("source_id", "Trace"), ("movement", "Movement"))
        elif stage == "t04":
            decisions = record.get("solution", {}).get("decisions", [])
            columns = (("route_id", "Route"), ("final_rung", "Rung"), ("original_width_mm", "Entry width (mm)"),
                       ("resulting_width_mm", "Result width (mm)"), ("blocking_reason", "Limit"))
        else:
            decisions = record.get("candidate", {}).get("decisions", [])
            columns = (("source_id", "Source"), ("status", "Decision"))
        if not decisions:
            return result
        rows = [tuple(escape(number(row[key])) if row.get(key) is not None else "—"
                      for key, _ in columns) for row in decisions[:30]]
        preview = table(tuple(label for _, label in columns), rows)
        if len(decisions) > len(rows):
            preview += f"<p>Showing {len(rows)} of {len(decisions)}. The stage JSON contains every decision.</p>"
        return result + f"<details><summary>Saved decisions</summary>{preview}</details>"

    def pass_stages(self, name):
        folder = self.job / name
        source = self.saved(folder / "source.json")
        previous = None
        sections = []
        if source:
            preview, previous = self.compare(name + "-entry", "Assembled stage entry", None,
                                             lambda: copper.scene_copper(folder, source["scene_ref"]), source=True)
            catalogue_id = source.get("source_catalogue_ref", {}).get("artifact_id")
            catalogue = folder / "runtime/artifacts" / catalogue_id if catalogue_id and Path(catalogue_id).name == catalogue_id else None
            catalogue_link = f"<p>{self.link(catalogue, 'Shared source catalogue')}</p>" if catalogue and catalogue.is_file() else ""
            sections.append(self.section("Stage entry", preview + self.artifacts([
                folder / "source.json", folder / "source_snapshot/top.art.gbr",
                *folder.glob("*SNAPSHOT.json"), *folder.glob("*BINDING.json"),
                *folder.glob("*POLICY.json"), *folder.glob("*SCHEDULE.json"),
            ]) + catalogue_link))
        for stage, title in STAGES.items():
            path = folder / f"{stage}.json"
            record = self.saved(path)
            preview, current = self.compare(f"{name}-{stage}", title, previous,
                (lambda: copper.scene_copper(folder, record["output_scene_ref"])) if record else None)
            evidence = [path, *folder.glob(f"audits/{stage}/*.json"),
                        *folder.glob(f"raw_checkpoints/{stage}_*.json")]
            if stage == "t04":
                evidence.extend([folder / "RAW_WIDTH_CHECKPOINT.json", folder / "T04_PRIOR_WIDTH_COMPATIBILITY.json",
                                 *folder.glob("width_prefix_audits/*.json")])
            if stage == "t05":
                evidence.extend(sorted(folder.glob("t05_search_checkpoints/*.json"))[-5:])
                evidence.extend(folder.glob("completion_checkpoints/t05_*_geometry.json"))
            checks = self.checks_table(f"{name}_{stage}_")
            sections.append(self.section(title, preview + self.stage_summary(stage, record) + checks + self.artifacts(evidence)))
            previous = current
        return "".join(sections), previous

    def export(self, name, before):
        folder = self.job / name
        target = folder / "export" / "top.art.gbr"
        proof_file = folder / "export" / "proof_1.json"
        proof = self.saved(proof_file)
        if not proof and name == "reference":
            proof = self.saved(folder / "export" / "proof_construct.json")
        show = (lambda: copper.exported_copper(folder, proof)) if proof and target.is_file() else None
        title = {"legacy": "First-pass Gerber and reparse", "reference": "Job-local remedy reference",
                 "connected": "Final Gerber and reparse"}[name]
        preview, after = self.compare(f"{name}-export", title, before, show)
        prefix = {"legacy": "legacy_legacy_export_", "reference": "reference_remedy_",
                  "connected": "connected_export_"}[name]
        evidence = [*folder.glob("export/*"), *folder.glob("*POLICY*.json")]
        return self.section(title, preview + self.checks_table(prefix) + self.artifacts(evidence)), after

    def delivery(self):
        folder = self.job / "connected"
        receipt = self.state.get("delivery") or self.saved(folder / "DELIVERY.json")
        images = [(name, folder / "visual" / filename) for name, filename in (
            ("Final source / growth comparison", "corrected_growth.png"),
            ("Source", "source.png"),
            ("Pocket repairs", "pocket_repairs.png"),
            ("Pocket close-ups", "pocket_detail_comparison.png"),
            ("Rejected corruption control", "rejected_source_void_control.png"),
        )]
        gallery = "".join(self.image(path, name) for name, path in images if path.is_file())
        links = []
        for label, key in (("Delivered Gerber", "gerber"), ("Delivered 4× render", "render")):
            if key in receipt and Path(receipt[key]).is_file():
                links.append(self.link(Path(receipt[key]), label))
        controls = self.saved(folder / "negative_controls" / "RESULT.json")
        control_files = [*folder.glob("negative_controls/*")]
        defects = folder / "REMAINING_DEFECT_AUDIT.json"
        body = f"<p>{' · '.join(links)}</p>" if links else "<p>No delivered Gerber or render recorded at the original output path.</p>"
        if gallery:
            body += f"<div class='gallery'>{gallery}</div>"
        if controls:
            body += f"<p>Corruption controls {status_label(controls['status'])}</p>"
            rows = [(escape(row["control"]), escape(row["status"]), escape(str(row.get("reason", ""))))
                    for row in controls.get("controls", [])]
            if rows:
                body += "<details><summary>Corruption outcomes</summary>" + table(("Control", "Result", "Reason"), rows) + "</details>"
        body += "".join(self.checks_table(prefix) for prefix in (
            "connected_controls_", "connected_remaining_defects_", "connected_render_"
        ) if any(key.startswith(prefix) for key in self.checks))
        return self.section("Controls, final render and delivery", body + self.artifacts([
            *control_files, defects, folder / "DELIVERY.json", folder / "visual/RECEIPT.json",
        ]))

    def write(self, back=None):
        self.output.mkdir()
        assembly = self.assembly()
        legacy, previous = self.pass_stages("legacy")
        legacy_export, previous = self.export("legacy", previous)
        reference, _ = self.export("reference", previous)
        connected, previous = self.pass_stages("connected")
        connected_export, _ = self.export("connected", previous)
        sections = (
            ("assembly", "Source assembly", assembly),
            ("legacy", "First pass", legacy + legacy_export),
            ("reference", "Local reference", reference),
            ("connected", "Connected pass", connected + connected_export),
            ("delivery", "Controls and delivery", self.delivery()),
        )
        nav = "".join(f'<a href="#{key}">{title}</a>' for key, title, _ in sections)
        content = "".join(f'<section id="{key}"><h2>{title}</h2>{body}</section>'
                          for key, title, body in sections)
        back_link = f"<p>{self.link(back, 'All trials')}</p>" if back else ""
        error = self.state.get("error")
        finding = f"<p><code>{escape(error)}</code></p>" if error else ""
        phase = self.state.get("phase")
        phase_text = f" · {escape(phase)}" if phase else ""
        receipts = self.artifacts([self.job / filename for filename in (
            "STATUS.current.json", "HALTED.json", "TRIAL_TIMEOUT.json"
        )], "Job receipts")
        unreadable = self.artifacts(self.unreadable, "Unreadable saved records")
        page(self.output / "index.html", "U05 job", back_link + f"<h1>U05 job</h1>"
             f"<p><code>{escape(self.job.name)}</code></p>"
             f"<p>{status_label(self.state['status'])}{phase_text}</p>{finding}{receipts}{unreadable}"
             f"<p>Saved evidence viewer. Copper additions are <span class='added'>green</span>"
             f" and removals are <span class='removed'>pink</span>.</p>"
             f"<nav aria-label='Job sections'>{nav}</nav>{content}")


def main():
    parser = argparse.ArgumentParser(description="View saved U05 stages, checks and delivery in an offline report.")
    parser.add_argument("source", type=Path, help="Job directory, STATUS.current.json, or synthetic suite directory")
    parser.add_argument("--output", type=Path, required=True, help="New report directory outside the saved input")
    parser.add_argument("--links-only", action="store_true", help="Link existing evidence and renders without drawing stage SVGs")
    parser.add_argument("--open", action="store_true", help="Open the report in the default browser")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if source.name == "STATUS.current.json" and source.is_file():
        source = source.parent
    output = args.output.resolve()
    if output.exists() or not output.parent.is_dir() or output.is_relative_to(source):
        parser.error("--output must be a new directory with an existing parent outside the saved input")
    index = output / "index.html"
    if (source / "STATUS.current.json").is_file():
        Report(source, output, args.links_only).write()
    else:
        receipts = sorted(source.glob("*/work/operator_routes/gerber_u05/*/STATUS.current.json"))
        suite_receipt = source / "SUITE.json"
        suite = read(suite_receipt) if suite_receipt.is_file() else {}
        results = {row["case"]: row for row in suite.get("results", [])}
        if not receipts and not results:
            parser.error("no saved job or synthetic trial suite at the supplied path")
        output.mkdir()
        rows = []
        seen = set()
        for receipt in receipts:
            job = receipt.parent
            case = job.parents[3].name
            seen.add(case)
            report = Report(job, output / f"{case}-{job.name}", args.links_only)
            report.write(back=index)
            path = quote(str((report.output / "index.html").relative_to(output)))
            passed = sum(row["status"] == "PASS" for row in report.checks.values())
            result = results.get(case, {})
            rows.append((f'<a href="{path}">{escape(case)}</a>', status_label(report.state["status"]),
                         str(passed), "Recorded" if report.state.get("delivery") else "—",
                         status_label(result["verdict"]) if result else "—",
                         escape(number(result.get("seconds", "—")))))
        for case in sorted(results.keys() - seen):
            result = results[case]
            rows.append((escape(case), "No saved job", str(result["checks_passed"]), "—",
                         status_label(result["verdict"]), escape(number(result["seconds"]))))
        summary = ""
        if suite:
            link = quote(os.path.relpath(suite_receipt, output))
            summary = f'<p>{escape(number(suite["seconds"]))} s · <a href="{link}">Suite receipt</a></p>'
        page(index, "U05 trial suite", "<h1>U05 trial suite</h1>" + summary
             + table(("Case", "Recorded status", "Checks passed", "Delivery", "Trial verdict", "Seconds"), rows))
    print(index)
    if args.open:
        webbrowser.open(index.as_uri())


if __name__ == "__main__":
    main()
