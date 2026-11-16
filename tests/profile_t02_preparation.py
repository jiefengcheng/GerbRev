"""Compare three preparation tasks on an accepted saved T02 entry; no growth search.

Each task revalidates artifact bytes, reconstructs complete neighbor records,
queries five target neighborhoods and assembles the exact ordered copper union.
The shared arm runs fresh task adapters on separate serial worker threads.
"""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter,process_time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext

from shapely import to_wkb
from shapely.geometry import box
from shapely.ops import unary_union
from src.gerber_u05.view_geometry import EvidenceStore
from src.stage_abi.runtime import operands
from src.stage_abi.lands import land_parameters
from src.stage_abi.store import canonical,digest
from src.stage_abi.preparation import worker_resources,prepared_tree
from src.stage_abi.t02_preparation import T02Preparation,predecessor_union
from src.u04_board.search import FastRectangleAdapter

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--saved-job',required=True,type=Path,help='Retained legacy job containing t02.json and audits/t02/proof.json')
parser.add_argument('--output',required=True,type=Path,help='New evidence directory on the configured workspace')
parser.add_argument('--baseline',choices=['fresh','shared'],default='fresh',
                    help='Fresh per-task preparation or cef312f shared preparation without packed unions')
args=parser.parse_args()
import os, shutil
workspace=Path(os.environ['GERBER_U05_WORKSPACE']).resolve(strict=True)
job=args.saved_job.resolve(strict=True)
dest=args.output.resolve()
if not dest.is_relative_to(workspace) or not job.is_relative_to(workspace):
    raise ValueError('T02_PROFILE_REQUIRES_CONFIGURED_WORKSPACE')
if shutil.disk_usage(workspace).free < 5*1024**3:
    raise ValueError('T02_PROFILE_WORKSPACE_RESERVE')
dest.mkdir(exist_ok=False)
stage=json.loads((job/'t02.json').read_bytes())
audit=json.loads((job/'audits/t02/proof.json').read_bytes())
assert audit['status']=='PASS' and audit['candidate_sha256']==digest(canonical(stage))
store=EvidenceStore(job)
scene=store.get_json(stage['plan']['scene_ref'],kind='scene')
assert audit['source_sha256']==scene['source_sha256']
policy=dict(stage='t02',parameters=land_parameters('t02'))
expected=stage['plan']['details']['shared_neighbor_gaps']
targets=stage['plan']['details']['targets'][:5]

def task(shared):
    wall,cpu=perf_counter(),process_time()
    scope=shared.task(scene,policy) if shared is not None else worker_resources(T02Preparation.key(scene,policy))
    with scope:
        rows,current,original=operands(store,scene)
        # New adapter per task: only the explicit shared preparation can
        # preserve these neighbor records across task boundaries.
        result=FastRectangleAdapter('t02')._shared_gap_records(store,scene,original,current)
        assert result==expected
        ids=sorted(current)
        geometries=[current[s] for s in ids]
        tree=prepared_tree(geometries)
        neighbors=[[ids[int(i)] for i in tree.query(current[s].envelope.buffer(.0401))]
                   for s in targets]
        image=predecessor_union(geometries,lambda:unary_union(geometries))
        signature=dict(records=digest(canonical(result)),neighbors=neighbors,image=digest(to_wkb(image)))
        result['groups'].clear() # cannot alter the retained immutable record
    return dict(wall_s=perf_counter()-wall,cpu_s=process_time()-cpu,signature=signature)

optimized_union=predecessor_union
def previous_shared_union(geometries,build):
    from src.stage_abi.t02_preparation import ACTIVE
    owner=ACTIVE.get()
    if owner is None:return build()
    return owner.resources.memo.construct('t02-predecessor-union',geometries,(),build)

records={}
for label in ('cold','shared'):
    rows=[]
    predecessor_union=previous_shared_union if label=='cold' and args.baseline=='shared' else optimized_union
    with T02Preparation(scene,policy) if label=='shared' or args.baseline=='shared' else nullcontext(None) as shared:
        wall,cpu=perf_counter(),process_time()
        # Separate worker threads explicitly receive the same session; the
        # lease serializes LRU access. No repeated full-board solve is run.
        for i in range(3):
            with ThreadPoolExecutor(max_workers=1) as worker:
                row=worker.submit(task,shared).result()
            rows.append(row);print(label,i+1,row['wall_s'],row['cpu_s'],flush=True)
        stats=shared.diagnostics() if shared else None
        records[label]=dict(tasks=rows,wall_s=perf_counter()-wall,cpu_s=process_time()-cpu,stats=stats)
    (dest/'PROGRESS.json').write_text(json.dumps(records,indent=2)+'\n')
expected_sig=records['cold']['tasks'][0]['signature']
assert all(row['signature']==expected_sig for result in records.values() for row in result['tasks'])
records.update(baseline=args.baseline,status='EXACT_PREPARATION_PARITY',source_sha256=scene['source_sha256'],
    predecessor_sha256=stage['plan']['scene_ref']['sha256'],scene_objects=len(scene['objects']),
    rectangle_targets=len(stage['plan']['details']['targets']),sample_neighbor_queries=len(targets),
    saved_neighbor_records_exact=True,full_board_run=False)
records['wall_saved_s']=records['cold']['wall_s']-records['shared']['wall_s']
records['wall_saved_percent']=100*records['wall_saved_s']/records['cold']['wall_s']
(dest/'RESULT.json').write_text(json.dumps(records,indent=2)+'\n')
print('COMPLETE',records['wall_saved_s'],records['wall_saved_percent'],flush=True)
