import ast, asyncio, json, pathlib, types
R=pathlib.Path(__file__).resolve().parents[2]
tree=ast.parse((R/'app/mri_autonomous/autonomous_multimarketplace_runner.py').read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AutonomousMultiMarketplaceRunner')
fn=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='execute_autonomous_order')
# Preserve exact prefix through the first SQLite initialization, stop before marketplace investigation.
stop=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.With))
fn.body=fn.body[:stop+1];fn.returns=None
for a in fn.args.args: a.annotation=None
calls=[]
class Sentinel(Exception): pass
def connect(path):
    calls.append(str(path));raise Sentinel('Intercepted before SQLite I/O')
ns={'MANDATORY_ORDER':'audit','time':types.SimpleNamespace(time=lambda:0),'datetime':__import__('datetime').datetime,'timezone':__import__('datetime').timezone,'logger':types.SimpleNamespace(info=lambda *a:None),'sqlite3':types.SimpleNamespace(connect=connect)}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'runner_exact_prefix','exec'),ns)
try: asyncio.run(ns[fn.name](types.SimpleNamespace(db_path=str(R/'data/sqlite/visibility.db'))))
except Sentinel: pass
out={'production_target_reached_sqlite_connect_without_guard':calls,'actual_sqlite_io':False,'method':'exact AST prefix through first with; sqlite connect replaced by raising sentinel'}
pathlib.Path(__file__).with_name('writer_probe.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))

