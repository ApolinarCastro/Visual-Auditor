import ast, asyncio, hashlib, json, pathlib, re, sqlite3, types
from typing import *
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
R=pathlib.Path(__file__).resolve().parents[2];E=pathlib.Path(__file__).resolve().parent
tree=ast.parse((R/'app/mri_dashboard/mri_api.py').read_text(encoding='utf-8'))
names={'clean_cat_title','normalize_title_tokens','extract_title_from_url','fetch_run_publications','get_history_run_publications','get_multimarketplace_summary'}
nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
for n in nodes:n.decorator_list=[]
def conn():
    c=sqlite3.connect((E/'phase_b_snapshot.db').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
ns=dict(globals(),get_sqlite_conn=conn,get_master_catalog=lambda:({},{},{},{}),orchestrator=types.SimpleNamespace(history=[]))
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'exact_api_functions','exec'),ns)
app=FastAPI();app.get('/api/history/{run_id}')(ns['get_history_run_publications']);app.get('/api/multimarketplace/summary')(ns['get_multimarketplace_summary'])
async def main():
    result={'method':'Exact API functions mounted in isolated ASGI app; catalog maps empty; no full application startup or browser test','runs':[]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://audit') as c:
        for run in json.loads((R/'evidence/mri_autonomous_operation_019/MRI_019_RUNS_MANIFEST.json').read_text())['runs']:
            resp=await c.get('/api/history/'+run['run_id']);data=resp.json(); pubs=data.get('publications',[])
            result['runs'].append({'run_id':run['run_id'],'http_status':resp.status_code,'count':len(pubs),'unique_response_records':len({json.dumps(p,sort_keys=True) for p in pubs}),'response':data})
        result['summary']=(await c.get('/api/multimarketplace/summary')).json()
    har=R/'evidence/mri_rea_discovery_010/paris_search_capture.har';result['har_sha256']=hashlib.sha256(har.read_bytes()).hexdigest()
    (E/'api_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'runs':[{k:v for k,v in x.items() if k!='response'} for x in result['runs']],'har_sha256':result['har_sha256']}))
asyncio.run(main())

