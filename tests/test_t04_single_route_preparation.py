from functools import lru_cache
from unittest.mock import patch

from shapely import to_wkb
from shapely.geometry import box

from src.stage_abi.store import canonical
from src.t04_incremental import IncrementalRoutes
from src.t04_ladder import solve
from src.t04_settings import capture


SCHEDULE = [1, 1, 1, 1, 2, 2, 2]


def make_checker(single_route):
    cores = dict(a=box(0, 0, .1, .04), b=box(.145, 0, .245, .04), c=box(.5, 0, .6, .04))
    rows = [dict(id=sid, original=body, candidate=body, verified_original_width_mm=.1)
            for sid, body in cores.items()]
    fixed = [dict(id='fixed', geometry=box(.644, 0, .744, .04))]

    @lru_cache
    def build(sid, factor, envelope):
        return cores[sid] if factor == 1 else cores[sid].buffer((factor - 1) * .05)

    return IncrementalRoutes(rows, fixed, build, capture(), dict.fromkeys(cores, .1),
                             prepare_single_route=single_route)


def state(engine):
    return (engine.fallback.accepted_hash,
            {sid: to_wkb(body) for sid, body in engine.current.items()},
            canonical(engine.fallback.accepted_results))


def run_step(engine, sid, factor, *, passed):
    before = engine.fallback.proof_state()
    report = engine.evaluate(sid, factor)
    assert report['passed'] is passed
    assert all(a is b for a, b in zip(before, engine.fallback.proof_state()))
    if passed:
        engine.accept(sid, factor)
        assert engine.fallback.accepted_hash != before[2]
    else:
        assert engine.pending is None
    return canonical(report), state(engine)


def test_repeated_rejection_and_neighbor_commit_match_without_full_trial_preparation():
    baseline, prototype = (make_checker(mode) for mode in (False, True))
    scenarios = ((('a', 1.1), False), (('c', 1.1), False), (('a', 1.1), False),
                 (('b', 1.05), True), (('a', 1.1), False))
    with patch.object(prototype.fallback, 'prepare_trial', side_effect=AssertionError('full row scan')):
        for args, passed in scenarios:
            assert run_step(baseline, *args, passed=passed) == run_step(prototype, *args, passed=passed)
    assert prototype.fallback.pending_changes == {'a'}


def test_full_prescribed_schedule_preserves_ledger_and_accepted_proofs():
    outcomes = []
    for mode in (False, True):
        engine = make_checker(mode)
        ledger = solve(dict.fromkeys(engine.order, .1), capture(), engine.evaluate, engine.accept,
                       pass_increments=SCHEDULE)
        outcomes.append((canonical(ledger), state(engine),
                         canonical(engine.parent.check(engine.rows, materialize_scene=True))))
    assert outcomes[0] == outcomes[1]


def test_a_restored_accepted_state_restarts_local_dependency_tracking():
    outcomes = []
    for mode in (False, True):
        engine = make_checker(mode)
        saved = (engine.current.copy(), engine.versions.copy(), engine.rows, engine.fallback.proof_state())
        first = run_step(engine, 'a', 1.1, passed=False)
        run_step(engine, 'b', 1.05, passed=True)
        engine.current, engine.versions, engine.rows, proof = saved
        engine.fallback.restore_proof_state(proof)
        restored = run_step(engine, 'a', 1.1, passed=False)
        assert restored == first
        outcomes.append(restored)
    assert outcomes[0] == outcomes[1]


def test_geometry_outside_the_prepared_envelope_uses_the_exact_index():
    outcomes = []
    for mode in (False, True):
        engine = make_checker(mode)
        candidate = engine.current['a'].buffer(.03)
        with patch.object(engine, 'build', return_value=candidate):
            outcomes.append(run_step(engine, 'a', 1.1, passed=False))
        assert engine.fallback.index_fallbacks > 0
    assert outcomes[0] == outcomes[1]
