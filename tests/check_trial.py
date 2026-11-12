"""Exercise the deadline against a process with a running worker."""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.gerber_u05.trial import run_with_deadline


WORKER = """
import os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(30)
"""

COORDINATOR = """
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2]])
time.sleep(30)
"""


def process_running(pid):
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, check=False
    )
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")


def check(workspace):
    assert run_with_deadline([sys.executable, "-c", "raise SystemExit(7)"], 5) == 7
    with tempfile.TemporaryDirectory(dir=workspace) as directory:
        pid_file = Path(directory) / "worker.pid"
        command = [sys.executable, "-c", COORDINATOR, WORKER, str(pid_file)]
        assert run_with_deadline(command, 2) is None
        pid = int(pid_file.read_text())
        deadline = time.monotonic() + 2
        while process_running(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        if process_running(pid):
            os.kill(pid, signal.SIGKILL)
            raise AssertionError(f"Worker {pid} survived the trial deadline")
    print("PASS: deadline stopped the coordinator and its worker, and early exit codes are preserved")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
