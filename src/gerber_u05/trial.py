"""Run a U05 trial in an isolated process group with a wall-clock deadline."""
import os
import signal
import subprocess
import sys
from pathlib import Path

TRIAL_SECONDS = 300
TIMEOUT_EXIT = 124


def kill_group(pid):
    # The coordinator and its workers inherit this group, including workers
    # executing native geometry that cannot handle a Python interrupt.
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def stop_trial(child):
    kill_group(child.pid)
    child.wait()
    kill_group(child.pid)


def run_with_deadline(command, seconds):
    child = subprocess.Popen(command, start_new_session=True)
    try:
        code = child.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        stop_trial(child)
        return None
    except BaseException:
        stop_trial(child)
        raise
    if code != 0:
        kill_group(child.pid)
    return code


if __name__ == "__main__":
    from .run import run_job

    run_job(Path(sys.argv[1]), Path(sys.argv[2]))
