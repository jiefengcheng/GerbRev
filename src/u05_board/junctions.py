"""Shared T05 spindle parameters and source geometry context."""
from dataclasses import asdict
from pathlib import Path
from shapely.geometry import box
from src.stage_abi.store import canonical, digest
from src.stage_abi.spindle import SpindleAdapter, filled_circle
from src.junction_spindle_stage import CONTRACT
from src.u04_board.search import FastRectangleAdapter
from src.stage_abi.preparation import prepared_tree as STRtree


def parameters():return dict(asdict(CONTRACT),radius_scales=list(CONTRACT.radius_scales))


class NativeSpindleAdapter(SpindleAdapter):
    def describe(self):
        value=super().describe();value['implementation']=digest(canonical(value)+Path(__file__).read_bytes());return value
    def _context(self,store,scene,policy,details):
        key=(id(store),digest(canonical(dict(scene=scene,policy=policy))))
        if getattr(self,'_source_key',None)==key:
            references={r[field]['artifact_id']:r[field] for r in scene['objects'] for field in ('geometry_ref','original_ref')}
            for reference in references.values():store.get(reference,kind='geometry')
            return self._source_context
        value=super()._context(store,scene,policy,details);self._source_context=value;self._source_key=key;return value
    def plan(self,store,scene,policy,selection,bounds):
        if set(selection)!={'stage','scene_ref','source_ids'} or selection['stage']!='t05' or set(bounds)!={'max_source_objects','max_targets','max_evaluations','max_output_bytes','max_seconds'} or any(type(v) is not int or v<=0 for v in bounds.values()):raise ValueError('U05_SELECTION_OR_BOUNDS_INVALID')
        ids=selection['source_ids']
        if type(ids) is not list or len(ids)!=len(set(ids)) or len(ids)>bounds['max_targets'] or len(scene['objects'])>bounds['max_source_objects']:raise ValueError('U05_SELECTION_COVERAGE_INVALID')
        objects,current,original,crop=self._context(store,scene,policy,None);ordered=list(current);tree=STRtree([current[s] for s in ordered]);original_tree=STRtree([original[s] for s in ordered]);routes=[];covered_cache={}
        for sid in sorted(ids):
            if sid not in objects or objects[sid]['kind']!='trace':raise ValueError('U05_NATIVE_TRACE_REQUIRED')
            declared=objects[sid]['metadata'].get('land_ids')
            if type(declared) is not list or len(declared)!=len(set(declared)):raise ValueError('U05_EXPLICIT_SOURCE_CONTACTS_REQUIRED')
            lands=[];skipped=[]
            for lid in declared:
                if lid not in objects or not objects[lid]['metadata'].get('qualified_land') or objects[lid]['kind'] not in ('circle','rectangle','inclusive_rectangle'):raise ValueError('U05_UNQUALIFIED_LAND')
                core=original[lid];g=current[lid]
                if original[sid].intersection(core).area<=1e-12 or current[sid].intersection(g).area<=1e-12:raise ValueError('U05_ORIGINAL_CONTACT_NOT_ESTABLISHED')
                if objects[lid]['kind']=='circle' and not filled_circle(core):raise ValueError('U05_UNSUPPORTED_FILLED_CIRCLE')
                if objects[lid]['kind'] in ('rectangle','inclusive_rectangle') and not g.equals(box(*g.bounds)):raise ValueError('U05_UNSUPPORTED_RECTANGLE')
                for oi in original_tree.query(core.envelope):
                    other=ordered[int(oi)]
                    if other!=lid and core.equals(original[other]) and not g.equals(current[other]):raise ValueError('U05_LAND_ALIAS_CONFLICT')
                aliases=set(objects[lid]['metadata']['alias_source_ids'])
                if any(not original[a].equals(core) or not current[a].equals(g) for a in aliases):raise ValueError('U05_LAND_ALIAS_CHANGED')
                if lid not in covered_cache:covered_cache[lid]=FastRectangleAdapter.covered(g,lid,current,ordered,tree,aliases)
                (skipped if covered_cache[lid] else lands).append(lid)
            routes.append(dict(source_id=sid,land_ids=lands,covered_lands=skipped))
        return dict(routes=routes,bounds=bounds,protected_source_ids=sorted(objects),family=CONTRACT.family)
