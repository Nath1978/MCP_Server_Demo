# -*- coding: utf-8 -*-
"""
mcp_chatbot.py
MCP Chatbot client via stdio, fully configured via .env, using logging and robust error handling.
"""
import os
import socket
import asyncio
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv, find_dotenv
import nest_asyncio
from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Get local IP address

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

print("Local IP:", get_local_ip())

# Allow nested event loops (useful in notebooks)
nest_asyncio.apply()

# Load environment variables (automatically finds .env)
load_dotenv(find_dotenv())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# MCP server launch configuration from .env
MCP_SERVER_CMD = os.getenv("MCP_SERVER_CMD", "uv")
MCP_SERVER_ARGS = os.getenv("MCP_SERVER_ARGS", "run research_server.py").split()
MCP_SERVER_ENV = {
    key: os.getenv(key)
    for key in ("ANTHROPIC_API_KEY",)
    if os.getenv(key) is not None
} or None

# Anthropic client configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.warning("ANTHROPIC_API_KEY not set in .env. Direct Anthropic calls will be disabled.")
    anthropic_client = None
else:
    anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-7-sonnet-20250219")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))

class MCPChatBot:
    def __init__(self):
        self.session: ClientSession = None
        self.anthropic = anthropic_client
        self.available_tools: List[Dict[str, Any]] = []

    async def process_query(self, query: str):
        if not self.anthropic:
            logger.error("Cannot process query: Anthropic client not configured.")
            return
        logger.info("Processing user query: %s", query)
        messages = [{"role": "user", "content": query}]
        try:
            response = self.anthropic.messages.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                tools=self.available_tools,
                messages=messages
            )
        except Exception as e:
            logger.exception("Error sending query to Anthropic")
            return

        continue_processing = True
        while continue_processing:
            assistant_content = []
            for chunk in response.content:
                if chunk.type == "text":
                    print(chunk.text)
                    assistant_content.append(chunk)
                    if len(response.content) == 1:
                        continue_processing = False
                elif chunk.type == "tool_use":
                    assistant_content.append(chunk)
                    messages.append({"role": "assistant", "content": assistant_content})
                    tool_name = chunk.name
                    tool_args = chunk.input
                    tool_id = chunk.id
                    logger.info("Invoking tool '%s' with args %s", tool_name, tool_args)
                    try:
                        tool_resp = await self.session.call_tool(tool_name, arguments=tool_args)
                        result_content = tool_resp.content
                    except Exception as e:
                        logger.exception("Error invoking tool %s", tool_name)
                        result_content = "Error executing tool"

                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result_content
                        }]
                    })
                    try:
                        response = self.anthropic.messages.create(
                            model=MODEL_NAME,
                            max_tokens=MAX_TOKENS,
                            tools=self.available_tools,
                            messages=messages
                        )
                    except Exception as e:
                        logger.exception("Error resuming conversation after tool_use")
                        return

                    if len(response.content) == 1 and response.content[0].type == "text":
                        print(response.content[0].text)
                        continue_processing = False

    async def chat_loop(self):
        print("\nMCP Chatbot Started! (type 'quit' to exit)")
        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() == 'quit':
                    break
                await self.process_query(query)
            except Exception as e:
                logger.exception("Error in chat loop")
                print(f"Error: {e}")

    async def run(self):
        server_params = StdioServerParameters(
            command=MCP_SERVER_CMD,
            args=MCP_SERVER_ARGS,
            env=MCP_SERVER_ENV
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                self.session = session
                await session.initialize()
                try:
                    tool_list = await session.list_tools()
                    tools = tool_list.tools
                    logger.info("Connected to MCP server with tools: %s", [t.name for t in tools])
                    self.available_tools = [
                        {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
                        for t in tools
                    ]
                except Exception as e:
                    logger.exception("Failed to retrieve tool list from server")
                    return
                await self.chat_loop()

async def main():
    bot = MCPChatBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())

