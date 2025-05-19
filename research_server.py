# research_server.py
# -*- coding: utf-8 -*-
import os
import re
import json
import socket
import logging
from pathlib import Path
from dotenv import load_dotenv
import arxiv
from functools import wraps
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.middleware import Middleware

# — Load & config —
load_dotenv()
MCP_NAME = os.getenv("MCP_NAME", "research")
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", 8000))
PAPER_DIR = Path(os.getenv("PAPER_DIR", "papers"))
PAPER_DIR.mkdir(exist_ok=True)

# — Logging —
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# — Helpers & status —
def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except:
            return "127.0.0.1"

def sanitize_topic(topic: str) -> str:
    name = re.sub(r"[^0-9a-z_]+", "_", topic.lower().strip())
    return re.sub(r"_+", "_", name)

server_status = {
    "ip":        get_local_ip(),
    "port":      MCP_PORT,
    "transport": "sse",
    "status":    "initialized"
}

def tool_exception_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in tool {func.__name__}: {e}")
            return {"error": str(e)}
    return wrapper

# — Instantiate and register tools —
mcp = FastMCP(MCP_NAME)
logger.debug(f"FastMCP '{MCP_NAME}' created")

@mcp.tool()
@tool_exception_handler
def status():
    return server_status

@mcp.tool()
@tool_exception_handler
def search_papers(topic: str, max_results: int = 5):
    client = arxiv.Client()
    query = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )
    topic_dir = PAPER_DIR / sanitize_topic(topic)
    topic_dir.mkdir(exist_ok=True)
    info_path = topic_dir / "papers_info.json"
    try:
        existing = json.loads(info_path.read_text(encoding="utf-8"))
    except:
        existing = {}
    ids = []
    for paper in client.results(query):
        pid = paper.get_short_id()
        ids.append(pid)
        summary = (paper.summary or "").strip()
        if len(summary) > 1000:
            summary = summary[:1000] + "…"
        existing[pid] = {
            "title":     paper.title,
            "authors":   [a.name for a in paper.authors],
            "summary":   summary,
            "pdf_url":   paper.pdf_url,
            "published": paper.published.date().isoformat()
        }
    info_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return ids

@mcp.tool()
@tool_exception_handler
def extract_info(paper_id: str):
    if not re.match(r"^[0-9]+\.[0-9]+(?:v[0-9]+)?$", paper_id):
        return {"error": "Invalid paper ID format."}
    for d in PAPER_DIR.iterdir():
        p = d / "papers_info.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if paper_id in data:
                return data[paper_id]
    return {"error": f"Paper '{paper_id}' not found."}

# — Starlette app with explicit routing —
routes = [
    Mount("/sse/", app=mcp.sse_app()),
    Mount("/static", app=StaticFiles(directory="static"), name="static"),
    Route("/", endpoint=lambda request: FileResponse(Path("static/index.html")), methods=["GET"]),
]

@asynccontextmanager
async def lifespan(app):
    logger.info("🔄 Startup iniciado")
    yield
    logger.info("⏹ Shutdown completo")

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
]

app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)

# — Run —
if __name__ == "__main__":
    logger.info(f"Starting MCP SSE server on 0.0.0.0:{MCP_PORT}")
    import uvicorn
    uvicorn.run(
        "research_server:app",
        host="0.0.0.0",
        port=MCP_PORT,
        log_level="info",
        reload=True
    )
