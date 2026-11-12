"""Check the exact inventory and bytes of the bundled U05 policy resources."""
import hashlib
import json

from .guard import ROOT


def verify_resources():
    manifest_file = ROOT / "contracts/u05_resources.json"
    raw_manifest = manifest_file.read_bytes()
    expected = json.loads(raw_manifest)
    inventory = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "contracts").rglob("*")
        if path.is_file() and path != manifest_file
    }
    if inventory != set(expected):
        raise ValueError("U05_RESOURCE_INVENTORY_CHANGED")
    for name, expected_hash in expected.items():
        path = ROOT / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError("U05_RESOURCE_HASH_CHANGED:" + name)
    return {
        "status": "PASS",
        "files": len(expected),
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
    }
