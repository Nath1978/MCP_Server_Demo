# -*- coding: utf-8 -*-
"""
mcp_client.py
MCP client via stdio, configured using .env variables.
"""
import os
import asyncio
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import anthropic

# Load environment variables from .env
load_dotenv()

# Server launch configuration from .env
MCP_SERVER_CMD = os.getenv("MCP_SERVER_CMD", "uv")
# Default should be a space-separated string; split into list
MCP_SERVER_ARGS = os.getenv("MCP_SERVER_ARGS", "run example_server.py").split()
# Optional: pass through any environment variables needed by the server
MCP_SERVER_ENV = {
    # e.g., "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "")
}

# Initialize server parameters for stdio transport
server_params = StdioServerParameters(
    command=MCP_SERVER_CMD,
    args=MCP_SERVER_ARGS,
    env=MCP_SERVER_ENV or None,
)

# (Optional) Initialize Anthropic client if doing direct Claude calls
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise EnvironmentError("Missing ANTHROPIC_API_KEY in .env file")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

async def run():
    # Launch the MCP server subprocess and acquire stdio streams
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Perform handshake
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print(f"Available MCP tools: {tools}")

            # Example: call a tool directly
            example_topic = os.getenv("EXAMPLE_TOPIC", "machine learning")
            result = await session.call_tool(
                "search_papers", {"topic": example_topic, "max_results": 3}
            )
            print(f"search_papers(\"{example_topic}\"): {result}\n")

            # Here you could integrate your async chat loop or further calls

if __name__ == "__main__":
    asyncio.run(run())
