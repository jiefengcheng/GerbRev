"""Lossless local evidence storage for the saved T04 diagnostic."""
import gzip
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from src.stage_abi.store import ArtifactStore, digest


class ReplayEvidence(ArtifactStore):
    compressed_kinds = {"width-check", "t04-pass-state"}

    def __init__(self, root):
        super().__init__(root)
        self.last_report = None

    def put(self, kind, blob):
        if kind not in self.compressed_kinds:
            return super().put(kind, blob)
        sha256 = digest(blob)
        artifact_id = f"{kind}:{sha256}"
        ref = dict(artifact_id=artifact_id, sha256=sha256)
        path = self.root / "artifacts" / (artifact_id + ".gz")
        with self._lock("artifact-" + sha256):
            if path.is_symlink():
                raise ValueError("T04_REPLAY_EVIDENCE_SYMLINK")
            if path.exists():
                if self.get(ref, kind=kind) != blob:
                    raise ValueError("T04_REPLAY_EVIDENCE_CHANGED")
            else:
                compressed = gzip.compress(blob, compresslevel=1, mtime=0)
                if shutil.disk_usage(path.parent).free < 5 * 1024**3 + len(compressed):
                    raise ValueError("T04_REPLAY_EVIDENCE_RESERVE")
                with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                    temp = Path(stream.name)
                    try:
                        stream.write(compressed)
                        stream.flush()
                        os.fsync(stream.fileno())
                        if gzip.decompress(temp.read_bytes()) != blob:
                            raise ValueError("T04_REPLAY_EVIDENCE_CHANGED")
                        os.link(temp, path)
                        fd = os.open(path.parent, os.O_RDONLY)
                        try:
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                    finally:
                        temp.unlink()
        if kind == "width-check":
            self.last_report = ref
        return ref

    def get(self, reference, *, kind=None):
        artifact_id = reference["artifact_id"]
        actual_kind, sha256 = artifact_id.split(":", 1)
        if actual_kind not in self.compressed_kinds:
            return super().get(reference, kind=kind)
        if (kind is not None and kind != actual_kind or sha256 != reference["sha256"]
                or len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256)):
            raise ValueError("T04_REPLAY_EVIDENCE_REFERENCE")
        path = self.root / "artifacts" / (artifact_id + ".gz")
        if path.is_symlink():
            raise ValueError("T04_REPLAY_EVIDENCE_SYMLINK")
        data = gzip.decompress(path.read_bytes())
        if digest(data) != sha256:
            raise ValueError("T04_REPLAY_EVIDENCE_CHANGED")
        return data

    def get_json(self, reference, *, kind=None):
        return json.loads(self.get(reference, kind=kind))
