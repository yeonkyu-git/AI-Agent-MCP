from __future__ import annotations

"""로깅 구성 모듈.

MCP 프로토콜은 stdout을 사용하므로, 애플리케이션 로그는 반드시 stderr로 분리해야 한다.
이 모듈은 단일 로거(`mcp-ansible`)를 생성/재사용하며 중복 핸들러 부착을 방지한다.
"""

import logging
import os
import sys


def configure_logging() -> logging.Logger:
    """서버 공용 로거를 초기화해 반환한다.

    환경 변수:
    - `ANSIBLE_MCP_LOG_LEVEL`: DEBUG/INFO/WARNING/ERROR (기본 INFO)

    Returns:
        logging.Logger: stderr 출력이 설정된 로거.
    """
    logger = logging.getLogger("mcp-ansible")

    # 이미 초기화된 경우(재호출/재import) 기존 객체를 그대로 반환한다.
    if logger.handlers:
        return logger

    level_name = os.getenv("ANSIBLE_MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # stdout은 MCP JSON-RPC 프레임 전용이므로 stderr 핸들러를 사용한다.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
