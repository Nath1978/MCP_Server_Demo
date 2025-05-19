# dbg_routes.py  (colócalo al lado de research_server.py y ejecútalo)
from research_server import mcp
for r in mcp.sse_app().routes:
    print(f"{r.path:20}  {r.methods}")
