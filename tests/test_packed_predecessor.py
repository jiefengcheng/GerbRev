"""Exact restoration, changed operands, corruption, and shared-budget controls."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from src.pin_separation import Rule, Slot
from src.prepared_land_scene import PreparedLandScene
from shapely import to_wkb, set_srid, set_precision, get_srid
from shapely.geometry import Point, box
from src.stage_abi.packed_geometry import PackedGeometry
from src.stage_abi.t02_preparation import T02Preparation, predecessor_union

SCENE = dict(source_sha256='a'*64, objects=[], lineage=[dict(stage='t04', hash='accepted')])
POLICY = dict(stage='t02', clearance=.04)


class PackedPredecessorTests(unittest.TestCase):
    def shape(self):
        return Point(0,0).buffer(1,quad_segs=512).difference(
            Point(0,0).buffer(.5,quad_segs=256))

    def test_exact_holes_srid_and_islands(self):
        shape=set_srid(self.shape().union(box(2,2,3,3)),4326)
        row=PackedGeometry.pack('binding',shape)
        result=row.restore()
        self.assertEqual(to_wkb(result,include_srid=True),to_wkb(shape,include_srid=True))
        self.assertEqual(get_srid(result),4326)

    def test_fixed_precision_uses_original_construction(self):
        shape=set_precision(box(0,0,1,1),.001)
        self.assertIsNone(PackedGeometry.pack('binding',shape))

    def test_corrupt_payload_and_metadata_rejected(self):
        row=PackedGeometry.pack('binding',self.shape())
        for bad in [replace(row,body=row.body[:-1]+b'x'),
                    replace(row,raw_size=row.raw_size+1),replace(row,key='other')]:
            with self.assertRaisesRegex(ValueError,'CORRUPTED'):bad.restore()

    def test_shared_budget_reuse_and_changed_operands(self):
        shape=self.shape();builds=[]
        with T02Preparation(SCENE,POLICY) as session:
            # Small test allowance forces the same oversize path as the real
            # 21.6 MB predecessor union, without a large synthetic artifact.
            session.memo_budget=32768
            session.resources.memo.limit=32768
            def build():builds.append(1);return shape
            with session.task(SCENE,POLICY):first=predecessor_union([shape],build)
            self.assertIsNotNone(session.packed_predecessor)
            # Fill the remaining ordinary memo too; the combined cap holds.
            with session.task(SCENE,POLICY):
                for n in range(30):session.resources.memo.buffer(box(n,0,n+1,1),.1)
                again=predecessor_union([shape],build)
            self.assertEqual(len(builds),1)
            self.assertEqual(to_wkb(first),to_wkb(again))
            self.assertLessEqual(session.resources.memo.weight+session.packed_predecessor.weight,32768)
            other=shape.buffer(.001)
            with session.task(SCENE,POLICY):
                updated=predecessor_union([other],lambda:other)
            self.assertEqual(to_wkb(updated),to_wkb(other))
            self.assertEqual(session.stats['packed_union_invalidations'],1)

    def test_corruption_closes_session_before_next_task(self):
        with T02Preparation(SCENE,POLICY) as session:
            session.memo_budget=32768;session.resources.memo.limit=32768
            shape=self.shape()
            with session.task(SCENE,POLICY):predecessor_union([shape],lambda:shape)
            session.packed_predecessor=replace(session.packed_predecessor,raw_sha='bad')
            with self.assertRaisesRegex(ValueError,'CORRUPTED'):
                with session.task(SCENE,POLICY):pass
            self.assertTrue(session.closed)

    def test_restored_predecessor_keeps_complete_clearance_and_pin_reports(self):
        core=Point(0,0).buffer(.1,quad_segs=128)
        neighbor=Point(.25,0).buffer(.1,quad_segs=128)
        source=core.union(neighbor)
        rule=Rule([Slot('a'*64,'slot',('pad','neighbor'),box(-.2,-.2,.45,.2),
                       source,(core,neighbor))],construction_gap=.0401,finished_gap=.04)
        def check():
            row=dict(id='pad',original=core,candidate=core,
                     native_source_kind='gr_circle',native_stroke_width_mm=0.)
            checker=PreparedLandScene([row],[dict(id='neighbor',geometry=neighbor)])
            with patch('src.pin_separation.ACTIVE',rule):
                return [checker.check([dict(row,candidate=c)],materialize_scene=True)
                        for c in [core,core.buffer(.004),core.buffer(.03)]]
        baseline=check()
        with T02Preparation(SCENE,POLICY) as session:
            session.memo_budget=32768;session.resources.memo.limit=32768
            for _ in range(2):
                with session.task(SCENE,POLICY):self.assertEqual(check(),baseline)
            self.assertEqual(session.stats['packed_union_hits'],1)
        self.assertEqual([r['passed'] for r in baseline],[True,True,False])
        self.assertFalse(baseline[-1]['pin_separation']['passed'])

    def test_oversize_fallback_remains_exact(self):
        with T02Preparation(SCENE,POLICY) as session:
            session.memo_budget=16;session.resources.memo.limit=16
            shape=self.shape();calls=[]
            for _ in range(2):
                with session.task(SCENE,POLICY):
                    def build():calls.append(1);return shape
                    self.assertEqual(to_wkb(predecessor_union([shape],build)),to_wkb(shape))
            self.assertEqual(len(calls),2)
            self.assertIsNone(session.packed_predecessor)


if __name__=='__main__':unittest.main()
