"""Ansible MCP 서버 패키지 초기화 모듈.

외부에서 `create_mcp_server`만 import 하면 서버 객체를 만들 수 있도록
공개 심볼을 최소화한다.
"""

from .mcp_router import create_mcp_server

__all__ = ["create_mcp_server"]
