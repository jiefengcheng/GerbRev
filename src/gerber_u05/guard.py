"""Hash-bound source jobs. Stored verdicts never replace fresh geometry checks."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def producer_files():
 files=[p for d in('src','contracts','tools','web')for p in(ROOT/d).rglob('*')if p.is_file()and p.suffix in('.py','.json','.command','.js','.html')]
 if(ROOT/'SOURCE_REVISION.json').exists():files.append(ROOT/'SOURCE_REVISION.json')
 return sorted(files)
def seal(run,profile):
 from src.hole_acceptance import capture as capture_holes,SNAPSHOT as HOLE_SNAPSHOT
 if not(run/HOLE_SNAPSHOT).exists():capture_holes(run)
 from src.t04_settings import capture_job,read_snapshot,SNAPSHOT_NAME
 if not(run/SNAPSHOT_NAME).exists():capture_job(run)
 read_snapshot(run/SNAPSHOT_NAME)
 from .ladder_continuation import capture_schedule,SCHEDULE
 if not(run/SCHEDULE).exists():capture_schedule(run)
 from .pipeline import save
 inputs=[run/name for name in('input_inventory.json','LEGACY_REFERENCE_JOB.json','CLEARANCE_SNAPSHOT.json','REMEDY_POLICY_SNAPSHOT.json','POLICY_SNAPSHOT.json','REFERENCE_BINDING.json','REFERENCE_CHANNELS.json','REUSED_PREFIX_BINDING.json','REUSED_T05_BINDING.json','REUSED_NATIVE_EXPORT_BINDING.json','REUSED_LEGACY_BINDING.json','REUSED_WIDTH_BINDING.json','SOURCE_ASSEMBLY_BINDING.json','PIN_SEPARATION_POLICY.json','T04_SETTINGS_SNAPSHOT.json','STORAGE_ENCODING.json')if(run/name).is_file()]
 inputs.append(run/HOLE_SNAPSHOT)
 inputs.extend(run/name for name in(SCHEDULE,'T04_RETAINED_PREFIX.json','T04_PREFIX_ORIGIN.json')if(run/name).is_file())
 save(run/'PRODUCER_BINDING.json',dict(job_inputs={str(p):sha(p)for p in inputs},schema='source-only-gerber-u05-producer/1',profile=profile,files={str(p):sha(p)for p in producer_files()},source_binding_sha256=sha(run/'source.json')))
def verify_sources(run):
 from importlib.metadata import version
 import shapely
 runtime=json.loads((ROOT/'contracts/gerber_u05/runtime.json').read_bytes())
 if {name:version(name)for name in runtime['packages']}!=runtime['packages']or shapely.geos_version_string!=runtime['geos']:raise ValueError('GERBER_U05_PINNED_RUNTIME_CHANGED')
 seal=json.loads((run/'PRODUCER_BINDING.json').read_bytes())
 if set(seal['files'])!={str(file)for file in producer_files()}:raise ValueError('GERBER_RUN_PRODUCER_NAMESPACE_CHANGED')
 for name,expected in seal['files'].items():
  if sha(name)!=expected:raise ValueError('GERBER_RUN_PRODUCER_CHANGED:'+name)
 for name,expected in seal.get('job_inputs',{}).items():
  if sha(name)!=expected:raise ValueError('GERBER_JOB_INPUT_CHANGED:'+name)
 if sha(run/'source.json')!=seal['source_binding_sha256']:raise ValueError('GERBER_RUN_SOURCE_BINDING_CHANGED')
 from .source_assembly import verify_run
 verify_run(run)
 if (run/'HALTED.json').exists():raise ValueError('HALTED_RUN_CANNOT_RESUME')
 if any(run.glob("REUSED_*_BINDING.json")):
  raise ValueError("STANDALONE_U05_REQUIRES_FRESH_SOURCE_JOB")
 from src.hole_acceptance import bind as bind_holes
 bind_holes(run)
 return seal

def install_read_fence(run):
 """Generation cannot open any retained result outside its own fresh job."""
 import os,sys
 from .workspace import configure
 workspace=configure(); protected=[workspace/'evidence', workspace/'operator_routes']; allowed=[Path(run).resolve()]
 # A normal app checkout contains out/evidence. Its source-root authority must
 # not accidentally grant access to every historical result nested underneath.
 if any(ROOT.resolve().is_relative_to(base) for base in protected):allowed.append(ROOT.resolve())
 assembly_binding=Path(run)/'SOURCE_ASSEMBLY_BINDING.json'
 if assembly_binding.exists():
  assembly_seal=json.loads((Path(run)/'PRODUCER_BINDING.json').read_bytes())
  if assembly_seal.get('job_inputs',{}).get(str(assembly_binding))!=sha(assembly_binding):raise ValueError('SOURCE_ASSEMBLY_READ_AUTHORITY_CHANGED')
  from .source_assembly import verify_run
  authority=verify_run(Path(run));allowed.append(Path(authority['assembly_run']).resolve())
 # Connected workers reconstruct their clearance-only T04 envelopes from the
 # freshly generated legacy sibling. Grant that exact sealed job-local role,
 # never the parent directory or arbitrary historical reservation inputs.
 reference=Path(run)/'REFERENCE_BINDING.json'
 if reference.exists():
  seal_value=json.loads((Path(run)/'PRODUCER_BINDING.json').read_bytes())
  if seal_value.get('job_inputs',{}).get(str(reference))!=sha(reference):raise ValueError('LOCAL_REFERENCE_READ_AUTHORITY_CHANGED')
  legacy=Path(run).parent/'legacy'
  if legacy.is_symlink()or legacy.resolve().parent!=Path(run).resolve().parent:raise ValueError('LOCAL_REFERENCE_MUST_BE_SAME_JOB')
  authority=json.loads(reference.read_bytes());source=json.loads((Path(run)/'source.json').read_bytes())
  if authority.get('schema')!='job-local-generated-reservation/1'or authority.get('source_only')is not True or authority.get('source_sha256')!=source['source_ref']['sha256']:raise ValueError('LOCAL_REFERENCE_SOURCE_AUTHORITY_CHANGED')
  legacy_seal=verify_sources(legacy)
  if legacy_seal.get('profile')!='fresh-legacy-reservation-reference/1'or json.loads((legacy/'source.json').read_bytes())['source_ref']!=source['source_ref']:raise ValueError('LOCAL_REFERENCE_ROLE_OR_SOURCE_CHANGED')
  allowed.append(legacy.resolve())
 def hook(event,args):
  if event!='open'or not isinstance(args[0],(str,bytes,os.PathLike)):return
  path=Path(os.fsdecode(args[0])).resolve()
  if any(path.is_relative_to(base) for base in protected)and not any(path.is_relative_to(p)for p in allowed):
   raise PermissionError('HISTORICAL_EVIDENCE_READ_FORBIDDEN:'+str(path))
 sys.addaudithook(hook)
