"""Exercise the real bounded context's input and end-of-loop guards."""
from shapely.geometry import box
from src.stage_abi.store import canonical, digest
from src.u05_board.coverage import CoverageAdapter


class Store:
    def __init__(self): self.verified = False
    def verify_reads(self): self.verified = True


class Snapshot:
    current = {}
    objects = {}
    def validate_bindings(self): pass
    def diagnostics(self): return {}


class Spatial:
    def validate_bindings(self, *args, **kwargs): pass
    def diagnostics(self): return {}


def fixture():
    store=Store(); scene={'objects': [], 'viewport_mm': [0,0,1,1]};policy={'stage':'t05'}
    adapter=CoverageAdapter(box(0,0,1,1))
    adapter._hot_key=(id(store),digest(canonical([scene,policy])))
    adapter._hot=({}, {}, {}, box(0,0,1,1));adapter._snapshot=Snapshot();adapter._spatial=Spatial();adapter._ids=[]
    return store,scene,policy,adapter


store,scene,policy,adapter=fixture()
with adapter.execution(store,scene,policy):
    assert adapter._context(store,scene,policy,None) == adapter._hot
    try: adapter._context(store,dict(scene),policy,None)
    except ValueError as e: assert str(e)=='U05_ATTACHMENT_EXECUTION_CONTEXT_CHANGED'
    else: raise AssertionError('foreign scene accepted')
assert store.verified

for mutation in ('scene','policy'):
    store,scene,policy,adapter=fixture()
    try:
        with adapter.execution(store,scene,policy):
            (scene if mutation=='scene' else policy)['unexpected_mutation']=True
    except ValueError as e: assert str(e)=='U05_ATTACHMENT_EXECUTION_INPUT_CHANGED'
    else: raise AssertionError(mutation+' mutation accepted')
print('PASS: execution validates bindings and rejects foreign or mutated inputs')
