"""Actual-data common-coordinate source/result/growth views; no geometry edits."""
import os,sys,json,copy,importlib.util,hashlib
from pathlib import Path
from . import exporter as e
p=e.p;visual_assets=p.ROOT;run=Path(sys.argv[1]);p.configure();selected_name=p.load(run/'input_inventory.json')['selected']
from .guard import install_read_fence
install_read_fence(run.parent)
inventory=p.load(run/'input_inventory.json');qualification_mode=inventory.get('qualification_mode','FULL_FRESH_SOURCE_ROUTE');reused_operations=0
stage_evidence='Every stage is freshly constructed and reconstructed twice from source. Final exported file is reparsed and checked twice.'
if qualification_mode != "FULL_FRESH_SOURCE_ROUTE":
 raise ValueError("STANDALONE_U05_REQUIRES_FRESH_SOURCE_JOB")
proofs=[p.load(run/'export'/('proof_'+str(i)+'.json'))for i in(1,2)]
if p.canonical(proofs[0])!=p.canonical(proofs[1])or proofs[0]['status']!='PASS':raise ValueError('TWO_NATIVE_PROOFS_REQUIRED')
body=(run/'export/top.art.gbr').read_bytes()
if p.digest(body)!=proofs[0]['generated_sha256']:raise ValueError('VISUAL_OUTPUT_BYTES_CHANGED')
e.verify_sources(run)
raw=(run/'source_snapshot/top.art.gbr').read_bytes();original,_,_=p.source_profile.parse_source(raw);n=len(original.objects)
source=p.affine_scale(p.source_profile.ordered((p.source_profile.object_geometry(o)[0],o.polarity_dark)for o in original.objects),1,-1,origin=(0,0))
base=(run/'reference/top.art.gbr').read_bytes()
if p.digest(base)!=p.load(run/'REFERENCE_BINDING.json')['generated_sha256']:raise ValueError('FRESH_REFERENCE_CHANGED')
prior_native=e.parse(base)
prior=source.union(p.unary_union([p.affine_scale(p.source_profile.object_geometry(o)[0],1,-1,origin=(0,0))for o in prior_native.objects[n:]]))
native=e.parse(body);new=[p.affine_scale(p.source_profile.object_geometry(o)[0],1,-1,origin=(0,0))for o in native.objects[n:]];store=e.p.Store(run/'runtime');after=p.geometry(store,proofs[0]['actual_material_image_ref']);growth=after.difference(source);repair=after.difference(prior);folder=run/'visual';folder.mkdir();os.environ['MPLCONFIGDIR']=str(folder/'matplotlib_cache')
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch
from shapely.geometry.polygon import orient
from src.growth_void_remedy_v09 import surface_parts
import numpy as np
BG='#102634';GRAY='#bac8ce';GREEN='#42f599'
def vector(shape):
 vertices=[];codes=[]
 for piece in surface_parts(shape):
  piece=orient(piece,sign=1.)
  for ring in [piece.exterior,*piece.interiors]:
   pts=np.asarray(ring.coords);vertices.extend(pts.tolist());codes.extend([PlotPath.MOVETO]+[PlotPath.LINETO]*(len(pts)-2)+[PlotPath.CLOSEPOLY])
 path=PlotPath(np.asarray(vertices).reshape((-1,2)),np.asarray(codes,dtype=np.uint8));path.should_simplify=False;return path
shapes=dict(source=source,prior=prior,after=after,growth=growth,repair=repair);paths={k:vector(v)for k,v in shapes.items()}
x,y,x1,y1=source.bounds;size=max(x1-x,y1-y);pad=size*.035;cx,cy=(x+x1)/2,(y+y1)/2;fit=[cx-size/2-pad,cy-size/2-pad,cx+size/2+pad,cy+size/2+pad]
def axes(ax,bounds,title=None):
 a,b,c,d=bounds;ax.set_facecolor(BG);ax.set_xlim(a,c);ax.set_ylim(d,b);ax.set_aspect('equal');ax.set_axis_off()
 if title:ax.set_title(title,color='white',fontsize=14,pad=12)
def draw(ax,key,color):ax.add_patch(PathPatch(paths[key],facecolor=color,edgecolor='none',linewidth=0,antialiased=True))
def single(name,basekey,delta=None):
 fig=Figure(figsize=(13,9) if name=='corrected_growth' else (10,10),dpi=720 if name=='corrected_growth' else 180,facecolor=BG);FigureCanvasAgg(fig);ax=fig.add_axes([0,0,1,1]);axes(ax,fit);draw(ax,basekey,GRAY)
 if delta:draw(ax,delta,GREEN)
 target=folder/(name+'.png');fig.canvas.print_png(target);fig.clear();return target
files=[single('source','source'),folder/'corrected_growth.png',single('pocket_repairs','after','repair')]
fig=Figure(figsize=(15,15),dpi=180,facecolor=BG);FigureCanvasAgg(fig)
details=sorted(surface_parts(repair),key=lambda x:(-x.area,x.wkb))[:3]
focuses=[]
for part in details:
 a,b,c,d=part.bounds;pad=max(c-a,d-b,.10)*.35;focuses.append([a-pad,b-pad,c+pad,d+pad])
while len(focuses)<3:focuses.append(fit)
marked=focuses[0]
for row,bounds in enumerate(focuses):
 for col,(key,title,delta)in enumerate((('source','Source',None),('prior','Prior U05',None),('after','Connected-copper correction — new fills in green','repair'))):
  ax=fig.add_subplot(3,3,row*3+col+1);axes(ax,bounds,title);draw(ax,key,GRAY)
  if delta:draw(ax,delta,GREEN)
fig.subplots_adjust(left=.015,right=.985,bottom=.025,top=.95,wspace=.04,hspace=.12);target=folder/'pocket_detail_comparison.png';fig.canvas.print_png(target);fig.clear();files.append(target)
# Relevant rejected control uses actual reparsed corruption bytes.
from src.hole_acceptance import required as holes_required
control_name='SOURCE_VOID_FILLED'if holes_required()else'FOREIGN_BRIDGE'
control_body=(run/'negative_controls'/(control_name+'.gbr')).read_bytes();control_native=e.parse(control_body);bad=p.unary_union([p.affine_scale(p.source_profile.object_geometry(obj)[0],1,-1,origin=(0,0))for obj in control_native.objects[len(e.parse(body).objects):]]);paths['bad_control']=vector(bad);cx,cy=bad.centroid.coords[0];control_bounds=[cx-.06,cy-.06,cx+.06,cy+.06]
fig=Figure(figsize=(12,6),dpi=180,facecolor=BG);FigureCanvasAgg(fig)
for col,title in enumerate(('Protected source hole','REJECTED — source hole fill')if holes_required()else('Original separate copper','REJECTED — foreign copper bridge')):
 ax=fig.add_subplot(1,2,col+1);axes(ax,control_bounds,title);draw(ax,'prior',GRAY)
 if col:draw(ax,'bad_control','#ff708a')
fig.subplots_adjust(left=.015,right=.985,bottom=.02,top=.93,wspace=.04);control_png=folder/'rejected_source_void_control.png';fig.canvas.print_png(control_png);fig.clear();files.append(control_png)
# Render at four times the 2340 × 1620 reference comparison size.
fig = Figure(figsize=(13, 9), dpi=720, facecolor=BG)
FigureCanvasAgg(fig)
for index, (key, title) in enumerate((("source", "Source"), ("after", "U05 · additions in green"))):
 ax = fig.add_subplot(1, 2, index + 1)
 axes(ax, fit, title)
 draw(ax, key, GRAY)
 if index == 1:
  draw(ax, "growth", GREEN)
fig.subplots_adjust(left=.02, right=.98, bottom=.02, top=.95, wspace=.03)
target = folder / "corrected_growth.png"
fig.canvas.print_png(target)
fig.clear()
receipt = dict(
 status="ACTUAL_PARSED_RESULT_VISUAL_AVAILABLE",
 qualification_mode=qualification_mode,
 stage_execution=stage_evidence,
 generated_sha256=p.digest(body),
 baseline_sha256=p.digest(base),
 source_sha256=p.digest(raw),
 added_growth_area_mm2=growth.area,
 added_repair_area_mm2=repair.area,
 renderer="Matplotlib Agg " + matplotlib.__version__,
 dimensions_px=[9360, 6480],
 files=[dict(path=str(f), sha256=p.digest(f.read_bytes())) for f in files],
 producer_sha256=p.digest(Path(__file__).read_bytes()),
 rendering_producer_binding_sha256=p.digest((run/"PRODUCER_BINDING.json").read_bytes()),
)
p.save(folder/"RECEIPT.json", receipt)
e.verify_sources(run)
print(json.dumps(receipt), flush=True)
