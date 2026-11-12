"""Place all job artifacts and caches under the explicitly selected workspace."""
import os
import shutil
import tempfile
from pathlib import Path

def configure():
    value = os.environ.get("GERBER_U05_WORKSPACE")
    if not value:
        raise RuntimeError("GERBER_U05_EXPLICIT_WORKSPACE_REQUIRED")
    work = Path(value).resolve(strict=True)
    if not work.is_dir():
        raise RuntimeError("GERBER_U05_WORKSPACE_MUST_BE_DIRECTORY")
    if shutil.disk_usage(work).free < 5 * 1024**3:
        raise RuntimeError("GERBER_U05_LOW_SPACE")
    tmp = work / "tmp"
    tmp.mkdir(exist_ok=True)
    os.environ.update(TMPDIR=str(tmp), TMP=str(tmp), TEMP=str(tmp),
                      PYTHONDONTWRITEBYTECODE="1", XDG_CACHE_HOME=str(work / "cache"))
    tempfile.tempdir = str(tmp)
    return work
