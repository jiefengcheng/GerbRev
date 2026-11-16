import copy
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from src.pin_separation import Rule, Slot
from shapely import to_wkb
from shapely.geometry import box

from src.stage_abi.preparation import decode_geometry, prepared_tree
from src.stage_abi.t02_preparation import T02Preparation, neighbor_records
from src.prepared_land_scene import PreparedLandScene

SCENE = dict(source_sha256='a'*64, objects=[], lineage=[dict(stage='t04', hash='accepted')])
POLICY = dict(stage='t02', clearance=.04)


class SharedT02Tests(unittest.TestCase):
    def test_workers_reuse_and_changed_geometry_misses(self):
        shape = box(0,0,1,1)
        with T02Preparation(SCENE, POLICY) as session:
            def task(extra=False):
                with session.task(SCENE, POLICY):
                    g = decode_geometry(to_wkb(shape))
                    if extra: g = g.buffer(.1)
                    tree = prepared_tree([g])
                    return id(g), id(tree), tree.query(box(.2,.2,.3,.3)).tolist()
            # Different executor workers lease the same in-process context.
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures=[workers.submit(task) for _ in range(2)]
                a,b=[f.result() for f in futures]
            self.assertEqual(a,b)
            self.assertEqual(session.resources.stats['index_builds'],1)
            self.assertEqual(session.resources.stats['spatial_hits'],1)
            changed=task(True)
            self.assertNotEqual(changed[:2],a[:2])
            self.assertEqual(session.resources.stats['index_builds'],2)

    def test_content_index_and_tree_owned_operand_survive_lru_eviction(self):
        with T02Preparation(SCENE,POLICY) as session:
            with session.task(SCENE,POLICY):
                shape=decode_geometry(to_wkb(box(0,0,1,1)))
                tree=prepared_tree([shape])
            session.resources.decoded.clear()
            session.resources.geometry_weight=0
            with session.task(SCENE,POLICY):
                restored=decode_geometry(to_wkb(box(0,0,1,1)))
                self.assertIs(restored,shape)
                self.assertIs(prepared_tree([box(0,0,1,1)]),tree)
                self.assertEqual(session.resources.stats['index_builds'],1)

    def test_index_order_invalidates_neighbor_positions(self):
        a,b=box(0,0,1,1),box(2,0,3,1)
        with T02Preparation(SCENE,POLICY) as session:
            with session.task(SCENE,POLICY):
                first=prepared_tree([a,b]);second=prepared_tree([b,a])
                self.assertEqual(first.query(a).tolist(),[0])
                self.assertEqual(second.query(a).tolist(),[1])
                self.assertEqual(session.resources.stats['index_builds'],2)

    def test_binding_and_cleanup(self):
        session=T02Preparation(SCENE,POLICY)
        changed=copy.deepcopy(SCENE);changed['lineage'][0]['hash']='changed'
        for scene,policy in [(changed,POLICY),(SCENE,dict(POLICY,clearance=.05))]:
            with self.assertRaisesRegex(ValueError,'PREDECESSOR_OR_POLICY_CHANGED'):
                with session.task(scene,policy):pass
        with session.task(SCENE,POLICY):pass
        session.close()
        with self.assertRaisesRegex(ValueError,'CLOSED'):
            with session.task(SCENE,POLICY):pass

    def test_records_are_copied_bound_and_corruption_rejected(self):
        shape=box(0,0,1,1);builds=[]
        with T02Preparation(SCENE,POLICY) as session:
            def build():builds.append(1);return dict(neighbors=['a'])
            def query(g):
                return neighbor_records(SCENE,{'x':shape},{'x':g},None,POLICY,build)
            with session.task(SCENE,POLICY):query(shape)['neighbors'].clear()
            with session.task(SCENE,POLICY):
                self.assertEqual(query(shape),dict(neighbors=['a']))
                query(shape.buffer(.01))
            self.assertEqual(len(builds),2)
            key=next(iter(session.records))
            session.records[key]=(b'{}','bad')
            with self.assertRaisesRegex(ValueError,'NEIGHBOR_CORRUPTED'):
                with session.task(SCENE,POLICY):pass
            self.assertTrue(session.closed)

    def test_exact_clearance_reports_with_fresh_task_checkers(self):
        core=box(0,0,.1,.1);neighbor=box(.15,0,.25,.1)
        source=core.union(neighbor)
        rule=Rule([Slot('a'*64,'protected',('pad','neighbor'),box(-.1,-.1,.35,.2),
                       source,(core,neighbor))],construction_gap=.0401,finished_gap=.04)
        def check():
            rows=[dict(id='pad',original=core,candidate=core,
                       native_source_kind='gr_poly',native_stroke_width_mm=0.)]
            checker=PreparedLandScene(rows,[dict(id='neighbor',geometry=neighbor)])
            reports=[]
            for candidate in [core,core.buffer(.004),core.buffer(.03)]:
                with patch('src.pin_separation.ACTIVE',rule):
                    reports.append(checker.check([dict(rows[0],candidate=candidate)],materialize_scene=True))
            return reports,to_wkb(checker.predecessor)
        baseline=check()
        with T02Preparation(SCENE,POLICY) as session:
            for _ in range(2):
                with session.task(SCENE,POLICY):
                    self.assertEqual(check(),baseline)
            self.assertGreater(session.resources.memo.stats['hits_t02-predecessor-union'],0)
        self.assertEqual([r['passed'] for r in baseline[0]],[True,True,False])
        self.assertFalse(baseline[0][-1]['pin_separation']['passed'])


if __name__ == '__main__':
    unittest.main()
