from . import pipeline as p

def required_coverage(store,stages,groups,contracts):
 from dataclasses import asdict
 rows=[];expected_radii=[c.notch_radius_mm for c in contracts]
 for stage,value in stages.items():
  actual=[]
  for record in value['intra']['rounds']:
   if record.get('status')=='RETAINED_SUCCESSFUL_CONSTRUCTION_PREFIX':actual.extend(record['radii_mm']);continue
   radius=record['radius_mm'];actual.append(radius);contract=next(c for c in contracts if c.notch_radius_mm==radius)
   if record['plan']['contract']!=asdict(contract):raise ValueError('QUALIFIED_REMEDY_ROUND_POLICY_CHANGED:'+stage)
  if actual!=expected_radii:raise ValueError('QUALIFIED_REMEDY_FROZEN_ROUND_ORDER_CHANGED:'+stage)
  for fill in value['intra']['fills']:
   own=fill['original_owner_id']
   if own not in groups:raise ValueError('QUALIFIED_REMEDY_ORIGINAL_OWNER_MISSING')
   logical=p.geometry(store,fill['logical_patch_ref']);body=groups[own]
   if hasattr(groups,'channels'):
    channel=fill.get('original_channel_id')
    if channel not in groups.channels:raise ValueError('QUALIFIED_REMEDY_FUNCTIONAL_OWNER_MISSING')
    body=groups.channels[channel]
   missing=logical.difference(body.buffer(contracts[0].file_uncertainty_mm)).area
   if missing>contracts[0].area_epsilon_mm2:raise ValueError('NATIVE_REQUIRED_POCKET_OR_NOTCH_MISSING:'+stage+':'+fill['source_id'])
   rows.append(dict(stage=stage,source_id=fill['source_id'],original_owner_id=own,missing_area_mm2=missing))
 return dict(passed=True,planned_owner_surface_updates=len(rows),records=rows,execution_policy='FROZEN_CONSECUTIVE_COMPONENTS_NO_REVISIT')
