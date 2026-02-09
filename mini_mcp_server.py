# mini_mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mini-mcp")

@mcp.tool()
def echo(text: str) -> str:
    """입력 텍스트를 그대로 반환"""
    return text

@mcp.tool()
def add(a: int, b: int) -> int:
    """두 정수 a, b를 더해서 반환"""
    return a + b


def main() -> None:
    # Run over stdio for Codex MCP integration
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
