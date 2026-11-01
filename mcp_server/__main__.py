"""python -m mcp_server: run the MCP server over stdio."""
from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run()
