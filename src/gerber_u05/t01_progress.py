"""Optional T01 worker telemetry, kept outside candidate and proof bytes."""
import json
import os
from time import monotonic


def reporter():
    if os.environ.get('U05_T01_PROGRESS') != '1':
        return None

    start = last = monotonic()

    def report(phase, **fields):
        nonlocal last
        now = monotonic()
        completed = fields.get('completed')
        if completed is not None and 0 < completed < fields['total']:
            if completed % 25 and now - last < 15:
                return
        if phase == 'allocation_round_checks' and fields['round_checks'] % 25 and now - last < 15:
            return
        last = now
        print(json.dumps(dict(status='T01_PROGRESS', phase=phase,
                              elapsed_seconds=round(now - start, 3), **fields)), flush=True)

    return report
