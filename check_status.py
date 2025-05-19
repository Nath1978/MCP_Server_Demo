# Minimal MCP TCP client for status tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio

server_params = StdioServerParameters(
    command="python",
    args=["research_server.py"],
    env=None,
)

async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"Available MCP tools: {tools}")
            result = await session.call_tool("status", {})
            print("Server status:", result)

if __name__ == "__main__":
    asyncio.run(run())
