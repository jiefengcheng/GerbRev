"""Additional channel constraints after the unchanged canonical source guard."""
import hashlib
from collections import OrderedDict
from shapely import STRtree, to_wkb
from shapely.ops import unary_union
from src.t01_canonical_surface import SurfaceGuard
from src.crop_square_neighbor_experiment import retain_attached
from src import source_channel_scope
from src.component_clearance import joined
from .checking_envelopes import constraint


class _ChannelScene:
    """Project accepted channel changes and query the resulting obstacles."""

    def __init__(self, functional, rows, scene):
        self.functional = functional
        self.source_ids = [row['id'] for row in rows]
        self.row_order = {sid: i for i, sid in enumerate(self.source_ids)}
        self.owners = tuple(functional.cores)
        self.owner_order = {owner: i for i, owner in enumerate(self.owners)}
        self.edits = {owner: {} for owner in self.owners}
        self.bodies = {}
        self.obstacles = {}
        self.buffers = OrderedDict()
        self.tree = None
        self.revision = 0
        for sid, shape in zip(self.source_ids, scene.original, strict=True):
            owner, addition = self._member(sid, shape)
            if addition is not None:
                self.edits[owner][sid] = addition
        for owner in self.owners:
            self._rebuild(owner)

    def _member(self, sid, shape):
        functional = self.functional
        if sid in functional.frame_ids:
            if to_wkb(shape) != to_wkb(functional.source_objects[sid]):
                raise ValueError('TEMPORARY_FRAME_GROWTH_NOT_ALLOWED:' + sid)
            return None, None
        original = functional.originals.get(sid)
        if original is not None and (original is shape or to_wkb(original) == to_wkb(shape)):
            return functional.owner(sid, shape), None
        ids = functional.ids.get(sid)
        if ids is None:
            ids = functional.assign(sid, shape)
        if len(ids) != 1:
            raise ValueError('DERIVED_MATERIAL_NOT_ONE_FUNCTIONAL_CHANNEL:' + sid)
        return ids[0], shape

    def _body(self, owner, edits):
        return joined([self.functional.cores[owner],
                       *(edits[sid] for sid in sorted(edits, key=self.row_order.__getitem__))])

    def _rebuild(self, owner):
        body = self._body(owner, self.edits[owner])
        self.bodies[owner] = body
        self.obstacles[owner] = constraint(self.functional, owner, body)
        self.buffers.pop(owner, None)
        self.tree = None

    def advance(self, scene):
        affected = set()
        # A commit only replaces the occurrence indices of that circle site.
        for record in scene.history[self.revision:]:
            for index in scene.sites[record['source_id']]['indexes']:
                sid = self.source_ids[index]
                owner, addition = self._member(sid, scene.shapes[index])
                if owner is None:
                    continue
                edits = self.edits[owner]
                if addition is not None and addition is not edits.get(sid):
                    edits[sid] = addition
                    affected.add(owner)
                elif addition is None and sid in edits:
                    del edits[sid]
                    affected.add(owner)
        for owner in affected:
            self._rebuild(owner)
        self.revision = scene.revision

    def neighbors(self, owner, window, overrides):
        # Counterfactuals overlay just their affected channels and leave the
        # accepted projection and its cached buffers intact.
        trial = {}
        for sid, shape in (overrides or {}).items():
            if sid not in self.row_order:
                continue
            affected, addition = self._member(sid, shape)
            if affected is None:
                continue
            edits = trial.setdefault(affected, dict(self.edits[affected]))
            if addition is None:
                edits.pop(sid, None)
            else:
                edits[sid] = addition
        trial_bodies = {key: self._body(key, edits) for key, edits in trial.items()}
        if self.tree is None:
            self.tree = STRtree([self.obstacles[key] for key in self.owners])
        foreign = {key: self.obstacles[key] for i in self.tree.query(window, predicate='intersects')
                   if (key := self.owners[i]) != owner and key not in trial}
        for key, body in trial_bodies.items():
            if key != owner:
                obstacle = constraint(self.functional, key, body)
                if obstacle.intersects(window):
                    foreign[key] = obstacle
        return trial_bodies.get(owner, self.bodies[owner]), {
            key: foreign[key] for key in sorted(foreign, key=self.owner_order.__getitem__)}

    def buffered(self, owner, obstacle, radius):
        if obstacle is not self.obstacles[owner]:
            return obstacle.buffer(radius, quad_segs=128)
        if owner not in self.buffers:
            self.buffers[owner] = obstacle.buffer(radius, quad_segs=128)
            if len(self.buffers) > 16:
                self.buffers.popitem(last=False)
        self.buffers.move_to_end(owner)
        return self.buffers[owner]


class ChannelSurfaceGuard(SurfaceGuard):
 def __init__(self, rows, shapes, sites):
  super().__init__(rows, shapes, sites)
  self.channel_scenes = {}

 def limit(self,site,proposal,scene,*,priority=False,record=True,overrides=None):
  functional=source_channel_scope.ACTIVE
  if functional is None:
   candidate=super().limit(site,proposal,scene,priority=priority,record=record,overrides=overrides)
   from src import pin_separation as pin
   if pin.ACTIVE is not None:
    material={r['id']:scene.shapes[i]for i,r in enumerate(self.rows)};material.update(overrides or {});proposed=dict(material);proposed[site['source_id']]=candidate
    if not pin.ACTIVE.growth_parts(material.values(),proposed.values())['passed']:candidate=site['core']
   return candidate
  # The canonical kernel and its pinned source hash remain unchanged. Run its
  # complete guard, then constrain optional copper by functional neighbours.
  canonical=super().limit(site,proposal,scene,priority=priority,record=False,overrides=overrides)
  sid=site['source_id'];core=site['core'];owner=functional.owner(sid,core)
  projection=self.channel_scenes.get(scene)
  if projection is None or projection.functional is not functional:
   projection=_ChannelScene(functional,self.rows,scene)
   self.channel_scenes[scene]=projection
  projection.advance(scene)
  radius=self.contract.construction_gap_mm+self.reserve
  owner_body,foreign=projection.neighbors(owner,proposal.buffer(radius).envelope,overrides)
  forbidden=unary_union([projection.buffered(other,g,radius)for other,g in foreign.items()])
  optional=canonical.difference(core).difference(forbidden)
  candidate,_=retain_attached(optional,core,scene.settings.kernel())
  candidate=unary_union([candidate,core.buffer(1e-10,quad_segs=128)])
  # Recheck the final, potentially clipped shape through the same canonical
  # surface predicate; priority is measured against the original round target.
  candidate=super().limit(site,candidate,scene,priority=False,record=False,overrides=overrides);held=[]
  if priority and candidate.symmetric_difference(proposal).area>scene.settings.area_epsilon:held.append('COMPLETE_ROUND_REQUIRED')
  if not candidate.covers(core):held.append('EXACT_CORE_CONTAINMENT')
  added=candidate.difference(owner_body)
  if any(not added.is_empty and added.distance(g)+self.contract.comparison_epsilon_mm<self.contract.construction_gap_mm for g in foreign.values()):held.append('FUNCTIONAL_SOURCE_CHANNEL_CLEARANCE')
  if held or candidate.difference(core).area<=scene.settings.area_epsilon:candidate=core
  from src import pin_separation as pin
  if pin.ACTIVE is not None:
   material={r['id']:scene.shapes[i]for i,r in enumerate(self.rows)}
   material.update({key:shape for key,shape in (overrides or {}).items() if key in material})
   proposed=dict(material);proposed[sid]=candidate
   proof=pin.ACTIVE.growth_parts(material.values(),proposed.values())
   if not proof['passed']:held.append('PROTECTED_PIN_SEPARATION_GROWTH');candidate=core
  if record:self.records.append(dict(source_id=sid,proposal_sha256=hashlib.sha256(to_wkb(proposal)).hexdigest(),candidate_sha256=hashlib.sha256(to_wkb(candidate)).hexdigest(),removed_optional_area_mm2=proposal.difference(candidate).area,held_reasons=held,construction_reserve_mm=self.reserve,functional_channel_id=owner,checked_foreign_functional_channels=sorted(foreign),unchanged_canonical_guard_candidate_sha256=hashlib.sha256(to_wkb(canonical)).hexdigest()))
  return candidate
