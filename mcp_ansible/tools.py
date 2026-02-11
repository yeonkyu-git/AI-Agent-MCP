from __future__ import annotations

"""MCP tool 정의 모듈.

주요 정책:
- 경로 직접 입력 금지: `playbook_id`, `inventory_id`만 허용
- 기본 실행은 check mode, apply는 분리 tool 사용
- 공통 실행 로직은 `_run`으로 통합
"""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .logging_config import configure_logging
from .registry_loader import RegistryError, RegistryLoader
from .runner_wrapper import execute_playbook

logger = configure_logging()

BASE_DIR = Path(__file__).resolve().parent
PLAYBOOK_REGISTRY_PATH = BASE_DIR / "configs" / "registry_playbooks.yaml"
INVENTORY_REGISTRY_PATH = BASE_DIR / "configs" / "registry_inventories.yaml"

# 서버 시작 시 레지스트리를 로드해 allow-list를 메모리에 고정한다.
registry = RegistryLoader(
    playbook_registry_path=PLAYBOOK_REGISTRY_PATH,
    inventory_registry_path=INVENTORY_REGISTRY_PATH,
)


def _run(
    *,
    playbook_id: str,
    inventory_id: str,
    check_mode: bool,
    extra_vars: dict[str, Any] | None,
    limit: str | None,
    tags: str | None,
    skip_tags: str | None,
) -> dict[str, Any]:
    """공통 실행 루틴.

    - 입력 유효성 검증
    - ID -> 경로 해석
    - ansible-runner 실행
    - 정형 결과(dict) 반환
    """
    if extra_vars is not None and not isinstance(extra_vars, dict):
        raise ValueError("extra_vars must be an object")

    playbook_path = registry.resolve_playbook(playbook_id)
    inventory_path = registry.resolve_inventory(inventory_id)

    result = execute_playbook(
        playbook_path=playbook_path,
        inventory_path=inventory_path,
        check_mode=check_mode,
        extra_vars=extra_vars,
        limit=limit,
        tags=tags,
        skip_tags=skip_tags,
    )
    return result.to_dict()


def register_tools(mcp: FastMCP) -> None:
    """MCP 서버에 공개 tool들을 등록한다."""

    @mcp.tool()
    def list_registered_playbooks() -> dict[str, str]:
        """허용된 playbook ID 목록을 반환한다.

        운영자가 레지스트리에 등록한 allow-list를 조회할 수 있다.
        """
        return registry.list_playbooks()

    @mcp.tool()
    def list_registered_inventories() -> dict[str, str]:
        """허용된 inventory ID 목록을 반환한다."""
        return registry.list_inventories()

    @mcp.tool()
    def run_playbook_check(
        playbook_id: str,
        inventory_id: str,
        extra_vars: dict[str, Any] | None = None,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
    ) -> dict[str, Any]:
        """allow-list 기반 playbook을 check mode로 실행한다.

        이 도구가 기본 안전 경로다. 실제 변경 없이 영향 범위를 먼저 확인할 때 사용한다.
        """
        try:
            return _run(
                playbook_id=playbook_id,
                inventory_id=inventory_id,
                check_mode=True,
                extra_vars=extra_vars,
                limit=limit,
                tags=tags,
                skip_tags=skip_tags,
            )
        except RegistryError as exc:
            logger.error("registry validation failed: %s", exc)
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    def run_playbook_apply(
        playbook_id: str,
        inventory_id: str,
        extra_vars: dict[str, Any] | None = None,
        limit: str | None = None,
        tags: str | None = None,
        skip_tags: str | None = None,
    ) -> dict[str, Any]:
        """allow-list 기반 playbook을 apply 모드로 실행한다.

        실제 시스템 변경이 발생하므로, 보통 check 결과 검토 후에만 호출한다.
        """
        try:
            return _run(
                playbook_id=playbook_id,
                inventory_id=inventory_id,
                check_mode=False,
                extra_vars=extra_vars,
                limit=limit,
                tags=tags,
                skip_tags=skip_tags,
            )
        except RegistryError as exc:
            logger.error("registry validation failed: %s", exc)
            raise ValueError(str(exc)) from exc
