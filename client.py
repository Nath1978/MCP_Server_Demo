import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    url = "http://192.168.100.167:8000/sse"
    
    # 1. Abre canal SSE
    async with sse_client(url) as (read_stream, write_stream):
        # 2. Inicializa la sesión MCP
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 3. Lista herramientas disponibles
            tools_resp = await session.list_tools()
            tool_names = [t.name for t in tools_resp.tools]
            print("🔌 Conectado. Herramientas disponibles:", tool_names)

            # Ejemplo: llama a tu primera herramienta
            if tool_names:
                first = tool_names[0]
                result = await session.call_tool(first, arguments={})
                print(f"Resultado de {first!r}:", result)

if __name__ == "__main__":
    asyncio.run(main())
