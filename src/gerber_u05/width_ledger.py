"""Validate recorded T04 search witnesses."""

def verify_width_ledger(value,store):
 solution=value['solution'];evaluations=value['evaluations']
 if solution.get('schema')=='source-route-ten-step-width-ladder/1':
  from src.t04_ladder import solve
  from src.t04_settings import read_snapshot,SNAPSHOT_NAME
  from . import pipeline as p
  settings=read_snapshot(store.root.parent/SNAPSHOT_NAME)
  widths={row['route_id']:row['original_width_mm']for row in solution['decisions']}
  if len(solution['evaluations'])!=solution['evaluation_count']or len(evaluations)!=solution['geometry_evaluation_count']:raise ValueError('REUSED_COMPLETE_WIDTH_SEARCH_LEDGER_MISSING')
  if solution['evaluation_count']>settings.step_count*len(widths):raise ValueError('REUSED_LADDER_ATTEMPT_LIMIT_CHANGED')
  remaining=iter(evaluations);consumed=0
  def recorded_check(sid,factor):
   nonlocal consumed
   try:row=next(remaining)
   except StopIteration as error:raise ValueError('REUSED_COMPLETE_WIDTH_SEARCH_LEDGER_MISSING')from error
   if row['route_id']!=sid or row['factor']!=factor:raise ValueError('REUSED_WIDTH_SEARCH_WITNESS_CHANGED')
   consumed+=1;return store.get_json(row['report_ref'],kind='width-check')
  # Replay discrete arithmetic and every cap rejection, using all immutable
  # geometry reports already qualified by the three original native workers.
  # This is evidence validation, not a new geometry evaluation or search.
  actual=solve(widths,settings,recorded_check,
               pass_increments=solution.get('pass_increments'))
  if consumed!=len(evaluations)or p.canonical(actual)!=p.canonical(solution):raise ValueError('REUSED_WIDTH_SEARCH_WITNESS_CHANGED')
  return dict(schema=solution['schema'],attempts=solution['evaluation_count'],geometry_checks=consumed,routes=len(widths))
 if len(evaluations)!=solution['evaluation_count']or len(solution['evaluations'])!=len(evaluations):raise ValueError('REUSED_COMPLETE_WIDTH_SEARCH_LEDGER_MISSING')
 for index,(row,witness)in enumerate(zip(evaluations,solution['evaluations'])):
  report=store.get_json(row['report_ref'],kind='width-check')
  matched=witness['index']==index and witness['scales']==row['scales']and witness['report_sha256']==row['report_ref']['sha256']
  if not matched or witness['passed']!=report['passed']or witness['failures']!=report['failures']:raise ValueError('REUSED_WIDTH_SEARCH_WITNESS_CHANGED')
 return dict(schema=solution.get('schema','legacy-continuous-search'),attempts=len(evaluations))
