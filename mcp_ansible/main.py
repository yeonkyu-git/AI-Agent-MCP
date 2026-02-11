from __future__ import annotations

"""Ansible MCP 서버 실행 진입점.

이 모듈은 MCP Host가 프로세스를 띄웠을 때 가장 먼저 실행되는 엔트리포인트다.
FastMCP의 기본 전송은 stdio(JSON-RPC)이므로 별도 transport 설정 없이
`server.run()`만 호출하면 MCP tool 서버로 동작한다.
"""

from .mcp_router import create_mcp_server


def main() -> None:
    """stdio 기반 MCP 서버를 시작한다.

    처리 흐름:
    1. 라우터에서 MCP 서버 객체 생성
    2. 등록된 tool 메타데이터/핸들러 활성화
    3. stdio 루프로 진입하여 JSON-RPC 요청 처리
    """
    server = create_mcp_server()
    # FastMCP는 기본 transport가 stdio라 별도 지정이 없다.
    server.run()


if __name__ == "__main__":
    main()
