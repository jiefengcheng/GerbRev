from collections import OrderedDict
from types import SimpleNamespace
import copy

import unittest
from shapely import to_wkb, set_precision
from shapely.geometry import box, Polygon

from src.stage_abi.store import digest
from src.u03_board.visibility_records import VisibilityRecords


def cache(shape):
    version = digest(to_wkb(shape))
    checker = SimpleNamespace(binding='scene', use_width_union_window=True,
        original_union_cache_limit=1024, original={'neighbor': shape},
        visible_cache={'neighbor': (version, shape)}, geometries=OrderedDict())
    return VisibilityRecords(checker), version


class VisibilityRecordTests(unittest.TestCase):
    def test_exact_roundtrip_and_version_miss(self):
        for shape in [box(0,0,1,1), Polygon(), box(0,0,2,2).difference(box(.5,.5,1,1))]:
            with self.subTest(shape=shape.geom_type):
                records, version = cache(shape)
                records.restore(records.snapshot())
                self.assertEqual(to_wkb(records.get('neighbor', version)), to_wkb(shape))
                self.assertIsNone(records.get('neighbor', '0' * 64))

    def test_corruption_does_not_partially_publish(self):
        records, version = cache(box(0,0,1,1))
        packet = records.snapshot()
        records.restore(packet)
        prior = dict(records.records)
        bad = copy.deepcopy(packet)
        bad['records'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'RECORD_CHANGED'):
            records.restore(bad)
        self.assertEqual(records.records, prior)
        bad = copy.deepcopy(packet)
        bad['binding'] = 'changed-source-or-policy'
        with self.assertRaisesRegex(ValueError, 'BINDING_CHANGED'):
            records.restore(bad)
        self.assertEqual(records.records, prior)

    def test_restore_before_mode_selection(self):
        records, version = cache(box(0,0,1,1))
        packet = records.snapshot()
        records.checker.use_width_union_window = False
        records.restore(packet)
        self.assertIsNone(records.get('neighbor', version))
        records.checker.use_width_union_window = True
        self.assertIsNotNone(records.get('neighbor', version))

    def test_resnapshot_does_not_relabel_restored_mode(self):
        records, version = cache(box(0,0,1,1))
        records.restore(records.snapshot())
        records.checker.visible_cache.clear()
        self.assertEqual(len(records.snapshot()['records']), 1)
        records.checker.use_width_union_window = False
        self.assertEqual(records.snapshot()['records'], [])
        records.checker.use_width_union_window = True
        self.assertEqual(len(records.snapshot()['records']), 1)

    def test_changed_scene_and_policy_rejected(self):
        for field, value in [('binding', 'different-scene'), ('original_union_cache_limit', 0)]:
            records, version = cache(box(0,0,1,1))
            packet = records.snapshot()
            setattr(records.checker, field, value)
            with self.assertRaisesRegex(ValueError, 'BINDING_CHANGED'):
                records.restore(packet)
            self.assertEqual(records.records, {})

    def test_non_default_precision_uses_original_path(self):
        records, _ = cache(set_precision(box(0,0,1,1), .001))
        self.assertEqual(records.snapshot()['records'], [])


if __name__ == '__main__':
    unittest.main()
