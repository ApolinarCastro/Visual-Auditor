"""Reproduce audit 020 without imports of MRI writers or marketplace access."""
import ast, asyncio, hashlib, json, pathlib, sqlite3, subprocess
from starlette.responses import JSONResponse
R=pathlib.Path(__file__).resolve().parents[2]
E=pathlib.Path(__file__).resolve().parent
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
protected=['data/sqlite/visibility.db','data/mri_experience.db','data/experience.db','data/mri_history.json','data/mri_categories.json']
before={p:digest(R/p) for p in protected}
def backup(relative, name):
    source=sqlite3.connect((R/relative).as_uri()+'?mode=ro',uri=True)
    dest=sqlite3.connect(E/name);source.backup(dest);source.close();dest.row_factory=sqlite3.Row;return dest
prod=backup('data/sqlite/visibility.db','production_snapshot.db')
phase=backup('tmp/mri_019_phase_b/visibility_mri_019.db','phase_b_snapshot.db')
out={'production_before':before,'sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'runs':[]}
for i in range(1,4):
    p=R/f'evidence/mri_autonomous_operation_019/run_{i}_evidence.json'; j=json.loads(p.read_text(encoding='utf-8'));rid=j['run_id']
    counts={}
    examples=[]
    for table in ['mri_publications','mri_historical_publications']:
        counts[table]=[dict(r) for r in phase.execute(f'SELECT marketplace,count(*) n FROM {table} WHERE run_id=? GROUP BY marketplace',(rid,))]
        examples += [dict(r) for r in phase.execute(f'SELECT marketplace,marketplace_product_id,canonical_url,raw_source_id,evidence_type,commercial_attributes FROM {table} WHERE run_id=? AND marketplace IN (?,?) LIMIT 2',(rid,'Mercado Libre','Ripley'))]
    out['runs'].append({'run_id':rid,'artifact_sha256':digest(p),'marketplaces':j['marketplaces'],'persisted_counts':counts,'examples':examples})
cols=[r[1] for r in prod.execute('pragma table_info(mri_publications)')]
rid='run_va_mri_operational_integration_1792000336'
rows=[]
for table in ['mri_publications','mri_historical_publications']:
    rows += [tuple(r) for r in prod.execute(f'SELECT {",".join(cols)} FROM {table} WHERE run_id=?',(rid,))]
out['history']={'count':len(rows),'sha256':hashlib.sha256(json.dumps(sorted(rows,key=str),default=str).encode()).hexdigest()}
out['integrity']={}
for label,conn in [('production_copy',prod),('phase_b_copy',phase)]:
    out['integrity'][label]={'integrity_check':[tuple(r) for r in conn.execute('pragma integrity_check')],'foreign_key_check':[tuple(r) for r in conn.execute('pragma foreign_key_check')]};conn.close()
# Execute exact endpoint body independently: no app import, no writers, no network.
source=(R/'app/mri_dashboard/mri_api.py').read_text(encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='get_multimarketplace_summary')
node.decorator_list=[];ns={'JSONResponse':JSONResponse};exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(R/'app/mri_dashboard/mri_api.py'),'exec'),ns)
out['summary_endpoint_exact_body']=json.loads(asyncio.run(ns[node.name]()).body)
out['endpoint_has_storage_or_run_lookup']=False
out['production_after']={p:digest(R/p) for p in protected}
out['production_unchanged']=out['production_before']==out['production_after']
(E/'offline_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'runs':[{'run_id':r['run_id'],'counts':r['persisted_counts'],'examples':r['examples']} for r in out['runs']],'history':out['history'],'integrity':out['integrity'],'production_unchanged':out['production_unchanged'],'api_status':out['summary_endpoint_exact_body']['status']},ensure_ascii=False,indent=2))

