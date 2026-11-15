"""Verify an immutable completed-pass prefix before continuing T04.

Captured attempt reports retain their original evidentiary role. New proposals
run the normal incremental checker, and each worker freshly validates both the
restored entry and its complete selected scene.
"""
import json
from pathlib import Path

from src.stage_abi.store import ArtifactStore, canonical, digest
from src.t04_ladder import solve
from src.u03_board.assembly import CandidateSnapshot, CandidateTrace

SCHEDULE = 'T04_PASS_SCHEDULE.json'
PREFIX = 'T04_RETAINED_PREFIX.json'
ORIGIN = 'T04_PREFIX_ORIGIN.json'


def capture_schedule(run):
    from .guard import ROOT
    from .pipeline import save
    value = json.loads((ROOT / 'contracts/t04/pass_schedule.json').read_bytes())
    increments(value)
    save(Path(run) / SCHEDULE, value)


def increments(value):
    if (set(value) != {'schema', 'status', 'pass_increments', 'scope'}
            or value['schema'] != 'pcb-t04-pass-schedule/1'
            or value['status'] != 'PROVISIONAL'
            or value['pass_increments'] != [1, 1, 1, 1, 2, 2, 2]):
        raise ValueError('T04_CONTINUATION_SCHEDULE_CHANGED')
    return value['pass_increments']


def read_schedule(run):
    file = Path(run) / SCHEDULE
    return increments(json.loads(file.read_bytes())) if file.exists() else None


def verify_prefix(store, scene, widths, settings):
    run = store.root.parent
    if not (run / PREFIX).exists():
        return None
    if read_schedule(run) != [1, 1, 1, 1, 2, 2, 2]:
        raise ValueError('T04_PREFIX_THREE_FURTHER_PASSES_REQUIRED')
    prefix_bytes = (run / PREFIX).read_bytes()
    prefix = json.loads(prefix_bytes)
    origin = json.loads((run / ORIGIN).read_bytes())
    authority = json.loads((run / 'REUSED_LEGACY_BINDING.json').read_bytes())['original']
    original_bytes = (Path(authority['original_run']).parent / 'T04_FOUR_PASS_PREFIX.json').read_bytes()
    if (origin != dict(schema='t04-captured-prefix-origin/1',
                       prefix_sha256=digest(prefix_bytes),
                       original_run=authority['original_run'],
                       original_prefix_sha256=digest(original_bytes),
                       original_producer_binding_sha256=authority['original_producer_binding_sha256'])
            or canonical(json.loads(original_bytes)) != prefix_bytes
            or prefix['producer_inputs']['PRODUCER_BINDING.json'] != authority['original_producer_binding_sha256']):
        raise ValueError('T04_PREFIX_ORIGIN_CHANGED')
    for name in ('source.json', 't03.json', 'T04_SETTINGS_SNAPSHOT.json'):
        if digest((run / name).read_bytes()) != prefix['producer_inputs'][name]:
            raise ValueError('T04_PREFIX_PREDECESSOR_CHANGED:' + name)
    if (prefix['schema'] != 'live-t04-prefix-evidence/1'
            or prefix['qualification'] != 'COMPLETED_FOUR_PASS_PREFIX_REQUIRES_CONTINUATION_VERIFICATION'
            or prefix['source_sha256'] != scene['source_sha256']
            or prefix['route_order'] != sorted(widths)
            or prefix['original_widths_mm'] != widths
            or prefix['settings_sha256'] != settings.source_sha256
            or prefix['settings'] != settings.resolved()
            or len(prefix['completed_passes']) != 4
            or prefix['pending_route'] is not None
            or prefix['pending_candidate'] is not None
            or prefix['pending_excluded'] is not True):
        raise ValueError('T04_COMPLETE_FOUR_PASS_PREFIX_REQUIRED')
    reports = iter(prefix['checked_geometry_reports'])
    # A read-only view verifies original immutable report hashes once. The
    # normal store separately tracks every geometry used by the new worker.
    reader = ArtifactStore.__new__(ArtifactStore)
    reader.root = store.root

    def recorded_check(sid, factor):
        row = next(reports, None)
        if row is None or row['route_id'] != sid or row['factor'] != factor:
            raise ValueError('T04_PREFIX_CHECK_REPORT_ORDER_CHANGED')
        return reader.get_json(row['report_ref'], kind='width-check')

    replayed = solve(widths, settings, recorded_check,
                     pass_increments=[1, 1, 1, 1])
    if (next(reports, None) is not None
            or replayed['evaluations'] != prefix['completed_attempts']
            or replayed['passes'] != prefix['completed_passes']
            or replayed['selected_rungs'] != prefix['accepted_rungs']):
        raise ValueError('T04_PREFIX_COMPLETE_LEDGER_CHANGED')
    return prefix


def restore_entry(incremental, prefix, settings, widths):
    """Restore only final accepted factors, then freshly check the whole entry."""
    for sid in incremental.order:
        rung = prefix['accepted_rungs'][sid]
        factor = settings.rung(widths[sid], rung)['factor']
        candidate = incremental.build(sid, factor, True)
        incremental.parent.valid_geometry(candidate)
        if not candidate.covers(incremental.parent.original[sid]):
            raise ValueError('T04_PREFIX_ORIGINAL_TRACE_CORE_REMOVED')
        incremental.current[sid] = candidate
        incremental.versions[sid] = factor
        incremental.rows[incremental.positions[sid]] = CandidateTrace(
            sid, incremental.parent.original[sid], candidate,
            incremental.parent.widths[sid])
    check = incremental.parent.check(CandidateSnapshot(tuple(incremental.rows)),
                                     materialize_scene=True)
    voids = [dict(scope=d.scope, **d.source_voids.complete(
        incremental.current, incremental.versions)) for d in incremental.owner_checks]
    check['original_source_voids'] = voids
    if not check['passed'] or any(not value['passed'] for value in voids):
        raise ValueError('T04_RESTORED_PREFIX_FULL_ENTRY_REJECTED')
    incremental.seed_fallback(check)
    return check
