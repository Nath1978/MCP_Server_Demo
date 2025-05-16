# -*- coding: utf-8 -*-
"""
MCP-integrable tool module for arXiv paper search and info extraction,
with improved error handling, logging, and environment checks.
"""
import os
import re
import json
import logging
from typing import List, Union, Dict
from functools import wraps
from dotenv import load_dotenv
import arxiv
import anthropic

# Load environment and validate keys
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise EnvironmentError("Missing ANTROPIC_API_KEY in environment variables")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
PAPER_DIR = "papers"
MAX_SUMMARY_LENGTH = 1000  # characters

# Utility: sanitize topic names for filesystem

def _sanitize_topic(topic: str) -> str:
    sanitized = topic.lower().strip()
    sanitized = re.sub(r"[^a-z0-9_]+", "_", sanitized)
    return re.sub(r"_+", "_", sanitized)

# Decorator for catching and logging exceptions in tools

def tool_exception_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in {func.__name__}: {e}")
            return {"error": str(e)}
    return wrapper

# Tool Functions
@tool_exception_handler
def search_papers(topic: str, max_results: int = 5) -> List[str]:
    """
    Search arXiv for papers on a given topic, store metadata locally.
    """
    client = arxiv.Client()
    search = arxiv.Search(
        query=topic,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )

    # Directory setup
    dir_name = _sanitize_topic(topic)
    path = os.path.join(PAPER_DIR, dir_name)
    os.makedirs(path, exist_ok=True)

    file_path = os.path.join(path, "papers_info.json")

    # Load existing info
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            papers_info = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    # Fetch and process papers
    paper_ids = []
    for paper in client.results(search):
        pid = paper.get_short_id()
        paper_ids.append(pid)
        summary = paper.summary or ""
        summary = (summary[:MAX_SUMMARY_LENGTH] + "...") if len(summary) > MAX_SUMMARY_LENGTH else summary

        papers_info[pid] = {
            "title": paper.title,
            "authors": [author.name for author in paper.authors],
            "summary": summary,
            "pdf_url": paper.pdf_url,
            "published": paper.published.date().isoformat()
        }

    # Save updated info
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(papers_info, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(paper_ids)} papers to {file_path}")
    return paper_ids

@tool_exception_handler
def extract_info(paper_id: str) -> Union[str, Dict]:
    """
    Retrieve stored metadata for a given paper ID.
    """
    if not re.match(r"^[a-zA-Z0-9\-_]+(v\d+)?$", paper_id):
        return {"error": "Invalid paper ID format"}

    for topic_dir in os.listdir(PAPER_DIR):
        dir_path = os.path.join(PAPER_DIR, topic_dir)
        file_path = os.path.join(dir_path, "papers_info.json")
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    papers_info = json.load(f)
                if paper_id in papers_info:
                    return papers_info[paper_id]
            except (json.JSONDecodeError, FileNotFoundError):
                logger.warning(f"Skipping corrupted file: {file_path}")
                continue

    return {"error": f"Paper ID '{paper_id}' not found"}

# Tool schema for MCP server

tools = [
    {
        "name": "search_papers",
        "description": "Searches arXiv and stores metadata for a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "max_results": {"type": "integer", "default": 5}
            },
            "required": ["topic"]
        }
    },
    {
        "name": "extract_info",
        "description": "Gets stored metadata for a given arXiv paper ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paper_id": {"type": "string"}
            },
            "required": ["paper_id"]
        }
    }
]

# Execution and formatting

def execute_tool(tool_name: str, tool_args: dict) -> str:
    result = globals()[tool_name](**tool_args)
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    if isinstance(result, list):
        return ", ".join(result)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)

# Anthropic client init
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Query processing logic (refactored flag)

def process_query(query: str):
    messages = [{"role": "user", "content": query}]
    continue_flag = True
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        tools=tools,
        messages=messages,
        max_tokens=2048
    )

    while continue_flag:
        for chunk in response.content:
            if chunk.type == "text":
                print(chunk.text)
            elif chunk.type == "tool_use":
                tool_name = chunk.name
                logger.info(f"Invoking tool {tool_name} with {chunk.input}")
                tool_result = execute_tool(tool_name, chunk.input)
                messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": chunk.id, "content": tool_result} ]})
                response = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    tools=tools,
                    messages=messages,
                    max_tokens=2048
                )
        continue_flag = any(c.type == "tool_use" for c in response.content)

# Optional: chat_loop unchanged or moved into MCP server setup

if __name__ == "__main__":
    print("Starting MCP tool module test...\nType 'quit' to exit.")
    while True:
        q = input("Query: ")
        if q.strip().lower() == 'quit':
            break
        process_query(q)
        print()



