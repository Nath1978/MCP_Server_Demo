## research_server.py (Refactored with Status Tool)
# -*- coding: utf-8 -*-
"""
Optimized MCP "research" server using FastMCP, including a 'status' RPC tool for health checks.
Features:
 - Single MCP instantiation
 - Graceful shutdown with signal handling
 - 'status' tool exposing current server status
 - Centralized config / env var validation
 - Improved logging and YAML output
 - Type hints and docstrings
"""
import os
import re
import json
import logging
import signal
import socket
from pathlib import Path
from typing import List, Dict, Union, Optional
from functools import wraps
from dotenv import load_dotenv
import arxiv
from mcp.server.fastmcp import FastMCP
import yaml

# --- Configuration ---
load_dotenv()

MCP_NAME = os.getenv("MCP_NAME", "research")
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", 8000))
PAPER_DIR = Path(os.getenv("PAPER_DIR", "papers"))
MAX_SUMMARY_LENGTH = int(os.getenv("MAX_SUMMARY_LENGTH", 1000))
SERVER_STATUS_PATH = Path(os.getenv("SERVER_STATUS_PATH", "server_status.yaml"))

# Ensure output directory exists
PAPER_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Utility Functions ---

def get_local_ip() -> str:
    """Return LAN IP address or fallback to localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"


def sanitize_topic(topic: str) -> str:
    """Generate filesystem-safe directory name."""
    name = re.sub(r"[^0-9a-z_]+", "_", topic.lower().strip())
    return re.sub(r"_+", "_", name)


def dump_status(status: Dict[str, Union[str, int]]) -> None:
    """Write server status to YAML file."""
    with SERVER_STATUS_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(status, f)

# Decorator to handle exceptions in tools
def tool_exception_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in {func.__name__}: {e}")
            return {"error": str(e)}
    return wrapper

# --- MCP Server Initialization ---
ip_addr = get_local_ip()
mcp = FastMCP(MCP_NAME, transport="tcp", host=ip_addr, port=MCP_PORT)

# In-memory status dict
server_status: Dict[str, Union[str, int]] = {
    "ip": ip_addr,
    "port": MCP_PORT,
    "transport": "tcp",
    "status": "initialized"
}

def update_status(state: str) -> None:
    server_status["status"] = state
    dump_status(server_status)

@mcp.tool()
@tool_exception_handler
def status() -> Dict[str, Union[str, int]]:
    """
    Return current server status for health checks.
    """
    return server_status

@mcp.tool()
@tool_exception_handler
def search_papers(topic: str, max_results: int = 5) -> Union[List[str], Dict[str, str]]:
    """
    Search arXiv, cache metadata locally, return paper IDs.
    """
    client = arxiv.Client()
    query = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )
    topic_dir = PAPER_DIR / sanitize_topic(topic)
    topic_dir.mkdir(exist_ok=True)
    info_path = topic_dir / "papers_info.json"

    # Load existing data
    try:
        existing = json.loads(info_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}

    ids: List[str] = []
    for paper in client.results(query):
        pid = paper.get_short_id()
        ids.append(pid)
        summary = (paper.summary or "").strip()
        if len(summary) > MAX_SUMMARY_LENGTH:
            summary = summary[:MAX_SUMMARY_LENGTH] + "..."
        existing[pid] = {
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "summary": summary,
            "pdf_url": paper.pdf_url,
            "published": paper.published.date().isoformat()
        }

    info_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Indexed {len(ids)} papers for topic '{topic}'")
    return ids

@mcp.tool()
@tool_exception_handler
def extract_info(paper_id: str) -> Union[Dict, str]:
    """
    Retrieve metadata for a stored paper ID.
    """
    if not re.match(r"^[0-9]+\.[0-9]+(?:v[0-9]+)?$", paper_id):
        return {"error": "Invalid paper ID format."}

    for topic_dir in PAPER_DIR.iterdir():
        info_path = topic_dir / "papers_info.json"
        if not info_path.exists():
            continue
        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
            if paper_id in data:
                return data[paper_id]
        except json.JSONDecodeError:
            logger.warning(f"Skipped corrupt JSON: {info_path}")

    return {"error": f"Paper '{paper_id}' not found."}

# --- Graceful Shutdown Handler ---
shutdown_flag = False

def _shutdown(signum, frame):
    global shutdown_flag
    shutdown_flag = True
    logger.info("Shutdown signal received")

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, _shutdown)

# --- Main Execution ---
if __name__ == "__main__":
    update_status("starting")
    try:
        update_status("running")
        logger.info(f"MCP '{MCP_NAME}' listening on tcp://{ip_addr}:{MCP_PORT}")

        # Loop until shutdown_flag is set
        while not shutdown_flag:
            mcp.run_once(timeout=1)
    finally:
        update_status("stopped")
        logger.info("Server stopped gracefully")
