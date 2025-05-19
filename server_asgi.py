from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP

# 1. Instancia tu servidor MCP
mcp = FastMCP("Mi MCP Distribuido")

# 2. Monta el SSE endpoint en Starlette
app = Starlette(routes=[
    Mount("/", app=mcp.sse_app()),
])
