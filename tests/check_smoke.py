"""Validate the terminal receipt from a fresh CLI run of synthetic_top.gbr."""
import hashlib
import json
import struct
import sys
from pathlib import Path

EXPECTED_GERBER = "04c05bb1a8d3e54282175556c97501f04dd65e839331be676e24bc29e14070cb"

def verify_delivery(log, expected_gerber=None):
    state = json.loads(log.read_text().splitlines()[-1])
    assert state["status"] == "U05_EXPORT_REPARSE_CONTROLS_RENDER_PASSED"
    checks = state["checks"]
    assert len(checks) == 47
    for row in checks.values():
        assert row["status"] == "PASS" and row["returncode"] == 0
    for pass_name in ("legacy", "connected"):
        for stage in ("t01", "t03", "t04", "t02", "t05"):
            workers = [checks[f"{pass_name}_{stage}_{mode}"]["pid"] for mode in ("construct", "1", "2")]
            assert len(set(workers)) == 3
    delivery = state["delivery"]
    gerber = Path(delivery["gerber"]).read_bytes()
    assert hashlib.sha256(gerber).hexdigest() == state["generated_sha256"] == delivery["gerber_sha256"]
    if expected_gerber is not None:
        assert state["generated_sha256"] == expected_gerber
    image = Path(delivery["render"]).read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n" and image[12:16] == b"IHDR"
    assert struct.unpack(">II", image[16:24]) == (9360, 6480)
    assert hashlib.sha256(image).hexdigest() == delivery["render_sha256"]
    return state

def check(log):
    verify_delivery(log, EXPECTED_GERBER)
    print("PASS: 47 operations, upstream synthetic Gerber byte parity, verified 9360 × 6480 PNG")

if __name__ == "__main__":
    check(Path(sys.argv[1]))
