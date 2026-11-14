"""Check saved export binding and rejection of altered or incomplete files."""
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

from src.gerber_u05 import legacy_export as export
from src.gerber_u05.pipeline import digest


def check(workspace):
    with tempfile.TemporaryDirectory(dir=workspace) as directory:
        run = Path(directory)
        (run / "PRODUCER_BINDING.json").write_bytes(b'{"producer":"example"}')
        body = b"saved Gerber bytes"
        ledger = {"generated_sha256": digest(body), "records": []}
        export.save_constructed(run, body, ledger)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: export.load_constructed(run), range(2)))
        assert results == [(body, ledger), (body, ledger)]

        files = [
            run / "export/top.art.gbr",
            run / "export/ledger.json",
            run / "PRODUCER_BINDING.json",
            run / "export/construction_binding.json",
        ]
        for path in files:
            original = path.read_bytes()
            if path.name == "construction_binding.json":
                value = json.loads(original)
                value["generated_sha256"] = "0" * 64
                path.write_text(json.dumps(value))
            else:
                path.write_bytes(original + b" ")
            try:
                export.load_constructed(run)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Modified {path.name} was accepted")
            finally:
                path.write_bytes(original)
        (run / "export/construction_binding.json").unlink()
        try:
            export.load_constructed(run)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Incomplete construction was accepted")
    with tempfile.TemporaryDirectory(dir=workspace) as directory:
        run = Path(directory)
        (run / "PRODUCER_BINDING.json").write_bytes(b'{"producer":"example"}')
        body = b"saved Gerber bytes"
        ledger = {"generated_sha256": digest(body), "records": []}
        export.save_constructed(run, body, ledger, {"expected_ref": "example"})
        assert export.load_constructed(run, require_model=True) == (body, ledger, {"expected_ref": "example"})
        model = run / "export/native_model.json"
        model.write_text('{"expected_ref":"changed"}')
        try:
            export.load_constructed(run, require_model=True)
        except ValueError:
            pass
        else:
            raise AssertionError("Modified native model was accepted")
        binding_path = run / "export/construction_binding.json"
        binding = json.loads(binding_path.read_bytes())
        del binding["native_model_sha256"]
        binding_path.write_text(json.dumps(binding))
        try:
            export.load_constructed(run, require_model=True)
        except ValueError:
            pass
        else:
            raise AssertionError("Missing native model binding was accepted")
    print("PASS: concurrent reads and rejection of changed or incomplete export bindings")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
