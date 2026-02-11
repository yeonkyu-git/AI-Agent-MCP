from __future__ import annotations

"""MCP 서버 라우팅 구성 모듈.

서버 이름과 tool 등록을 한 곳에서 관리한다.
실행 엔트리포인트(`main.py`)는 이 모듈을 통해 완성된 서버 객체를 전달받는다.
"""

from mcp.server.fastmcp import FastMCP

from .tools import register_tools


def create_mcp_server() -> FastMCP:
    """Ansible MCP 서버 인스턴스를 생성하고 tool을 등록한다.

    Returns:
        FastMCP: MCP Host가 연결할 수 있는 서버 객체.
    """
    mcp = FastMCP("ansible-mcp-server")
    register_tools(mcp)
    return mcp
