# -*- coding: utf-8 -*-
"""
research_server.py
Building your MCP Server using FastMCP with robust error handling and logging.
"""
import os
import re
import json
import logging
from typing import List, Union, Dict
from functools import wraps
from dotenv import load_dotenv
import arxiv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Validate and prepare constants
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # if you need Anthropic in future
PAPER_DIR = "papers"
MAX_SUMMARY_LENGTH = 1000  # truncate long summaries

# Ensure base directory exists
os.makedirs(PAPER_DIR, exist_ok=True)

# Utility: sanitize topic for filesystem
def _sanitize_topic(topic: str) -> str:
    sanitized = topic.lower().strip()
    sanitized = re.sub(r"[^a-z0-9_]+", "_", sanitized)
    return re.sub(r"_+", "_", sanitized)

# Decorator to catch and log exceptions in tool functions
def tool_exception_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in {func.__name__}: {e}")
            return {"error": str(e)}
    return wrapper

# Initialize FastMCP server
mcp = FastMCP("research")

@mcp.tool()
@tool_exception_handler
def search_papers(topic: str, max_results: int = 5) -> Union[List[str], Dict]:
    """
    Search arXiv for papers on a given topic, store metadata locally.
    Returns list of paper IDs or an error dict.
    """
    client = arxiv.Client()
    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )

    dir_name = _sanitize_topic(topic)
    path = os.path.join(PAPER_DIR, dir_name)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, "papers_info.json")

    # Load existing data
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            papers_info = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    paper_ids: List[str] = []
    for paper in client.results(search):
        pid = paper.get_short_id()
        paper_ids.append(pid)
        summary = paper.summary or ""
        if len(summary) > MAX_SUMMARY_LENGTH:
            summary = summary[:MAX_SUMMARY_LENGTH] + "..."

        papers_info[pid] = {
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "summary": summary,
            "pdf_url": paper.pdf_url,
            "published": paper.published.date().isoformat()
        }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(papers_info, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(paper_ids)} papers under '{dir_name}'")
    return paper_ids

@mcp.tool()
@tool_exception_handler
def extract_info(paper_id: str) -> Union[Dict, str]:
    """
    Retrieve metadata for a stored paper ID across all topics.
    Returns dict of info or error dict/string.
    """
    # Validate ID format e.g. '1310.7911v2'
    if not re.match(r"^[0-9]+\.[0-9]+(v[0-9]+)?$", paper_id):
        return {"error": "Invalid paper ID format. Expected format '1234.5678v2' or '1234.5678'."}

    for topic_dir in os.listdir(PAPER_DIR):
        dir_path = os.path.join(PAPER_DIR, topic_dir)
        file_path = os.path.join(dir_path, "papers_info.json")
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    papers_info = json.load(f)
                if paper_id in papers_info:
                    return papers_info[paper_id]
            except json.JSONDecodeError:
                logger.warning(f"Corrupted JSON skipped: {file_path}")
                continue

    return {"error": f"Paper ID '{paper_id}' not found."}

if __name__ == "__main__":
    logger.info("Starting MCP Research Server (stdio transport)")
    mcp.run(transport='stdio')

