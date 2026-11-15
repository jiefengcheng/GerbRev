"""Durable, job-bound accepted T04 pass state."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from shapely import from_wkb, get_precision, to_wkb

from src.stage_abi.store import canonical, digest
from src.t04_ladder import solve
from src.u03_board.assembly import CandidateTrace

KIND = 't04-pass-state'


class PassState:
    def __init__(self, store, directory, binding, *, first_pass=1):
        self.store = store
        self.directory = Path(directory)
        self.first_pass = first_pass
        self.binding = digest(canonical([binding, first_pass]))
        self.geometry_refs = {}

    def save(self, prefix, evaluations, checker):
        if checker.pending is not None:
            raise ValueError('T04_PASS_STATE_HAS_PENDING_PROPOSAL')
        fallback = checker.fallback
        physical = None
        if fallback is not None:
            current, proofs, proof_hash = fallback.proof_state()
            if current is None or any(current[sid] is not geometry for sid, geometry in checker.current.items()):
                raise ValueError('T04_PASS_STATE_UNACCEPTED_CLEARANCE')
            physical = dict(binding=fallback.binding, proof_hash=proof_hash, witnesses=proofs)
        refs = {}
        for sid, body in checker.current.items():
            version = checker.versions[sid]
            cached = self.geometry_refs.get(sid)
            if cached is None or cached[0] != version:
                if get_precision(body) != 0:
                    raise ValueError('T04_PASS_STATE_GEOMETRY_PRECISION_UNSUPPORTED')
                cached = version, self.store.put('geometry', to_wkb(body, include_srid=True))
            self.geometry_refs[sid] = cached
            refs[sid] = cached[1]
        number = len(prefix['completed_passes'])
        payload = dict(schema=KIND+'/1', binding=self.binding, number=number, prefix=prefix,
                       geometry=refs, physical=physical, evaluations=evaluations)
        ref = self.store.put_json(KIND, payload)
        if self.directory.is_symlink():
            raise ValueError('T04_PASS_STATE_UNSAFE_DIRECTORY')
        self.directory.mkdir(exist_ok=True)
        path = self.directory / f'{number:02d}.json'
        # Publish only a complete, synced artifact. Keep all prior pass markers.
        with NamedTemporaryFile(dir=self.directory, prefix='.pending-', delete=False) as stream:
            pending = Path(stream.name)
            stream.write(canonical(ref))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(pending, path)
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            pending.unlink()

    def latest(self):
        if self.directory.is_symlink():
            raise ValueError('T04_PASS_STATE_UNSAFE_DIRECTORY')
        markers = sorted(self.directory.glob('*.json'))
        if not markers:
            return None
        number = self.first_pass + len(markers) - 1
        if [path.name for path in markers] != [f'{i:02d}.json' for i in range(self.first_pass, number+1)]:
            raise ValueError('T04_PASS_STATE_SEQUENCE_CHANGED')
        marker = markers[-1]
        if marker.is_symlink():
            raise ValueError('T04_PASS_STATE_UNSAFE_MARKER')
        state = self.store.get_json(json.loads(marker.read_bytes()), kind=KIND)
        if (state['schema'], state['binding'], state['number']) != (KIND+'/1', self.binding, number):
            raise ValueError('T04_PASS_STATE_BINDING_CHANGED')
        return state

    def validate_ledger(self, state, widths, settings, schedule):
        prefix = state['prefix']
        attempts = iter(state['evaluations'])

        def recorded(sid, factor):
            row = next(attempts, None)
            if row is None or (row['route_id'], row['factor']) != (sid, factor):
                raise ValueError('T04_PASS_STATE_REPORT_ORDER_CHANGED')
            return self.store.get_json(row['report_ref'], kind='width-check')

        if not 1 <= state['number'] <= len(schedule):
            raise ValueError('T04_PASS_STATE_SCHEDULE_CHANGED')
        result = solve(widths, settings, recorded, pass_increments=schedule[:state['number']])
        if (next(attempts, None) is not None
                or result['passes'] != prefix['completed_passes']
                or result['evaluations'] != prefix['completed_attempts']
                or result['selected_rungs'] != prefix['accepted_rungs']):
            raise ValueError('T04_PASS_STATE_LEDGER_CHANGED')

    def restore(self, state, checker, settings, widths):
        restore_geometry(self.store, state['geometry'], checker, settings, widths,
                         state['prefix']['accepted_rungs'])
        self.geometry_refs = {sid: (checker.versions[sid], ref) for sid, ref in state['geometry'].items()}
        physical = state['physical']
        if (physical is None) != (checker.fallback is None):
            raise ValueError('T04_PASS_STATE_CLEARANCE_PROFILE_CHANGED')
        if physical is not None:
            if physical['binding'] != checker.fallback.binding:
                raise ValueError('T04_PASS_STATE_CLEARANCE_BINDING_CHANGED')
            checker.fallback.load_accepted_proofs(checker.rows, physical['witnesses'], physical['proof_hash'])


def restore_geometry(store, geometry_refs, checker, settings, widths, rungs):
    if set(geometry_refs) != set(checker.order) or set(rungs) != set(checker.order):
        raise ValueError('T04_PASS_STATE_ROUTE_COVERAGE_CHANGED')
    for sid in checker.order:
        candidate = from_wkb(store.get(geometry_refs[sid], kind='geometry'))
        checker.parent.valid_geometry(candidate)
        factor = settings.rung(widths[sid], rungs[sid])
        if not factor['within_growth_limits'] or not candidate.covers(checker.parent.original[sid]):
            raise ValueError('T04_PASS_STATE_ROUTE_CHANGED')
        checker.current[sid] = candidate
        checker.versions[sid] = factor['factor']
        checker.rows[checker.positions[sid]] = CandidateTrace(
            sid, checker.parent.original[sid], candidate, checker.parent.widths[sid])
