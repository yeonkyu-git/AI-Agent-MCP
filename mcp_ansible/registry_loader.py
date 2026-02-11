from __future__ import annotations

"""레지스트리 YAML 로더.

보안 목적상 사용자 입력으로 파일 경로를 직접 받지 않고,
미리 등록된 ID만 허용하기 위한 allow-list 레이어다.
"""

from pathlib import Path
from typing import Any

import yaml


class RegistryError(ValueError):
    """레지스트리 형식/조회 오류를 나타내는 예외."""


class RegistryLoader:
    """playbook/inventory 레지스트리를 읽고 ID를 경로로 해석한다."""

    def __init__(self, playbook_registry_path: Path, inventory_registry_path: Path) -> None:
        """레지스트리 파일을 로드한다.

        Args:
            playbook_registry_path: `playbooks` 목록이 들어있는 YAML 경로.
            inventory_registry_path: `inventories` 목록이 들어있는 YAML 경로.
        """
        self.playbook_registry_path = playbook_registry_path
        self.inventory_registry_path = inventory_registry_path

        self._playbooks = self._load_registry(self.playbook_registry_path, "playbooks")
        self._inventories = self._load_registry(self.inventory_registry_path, "inventories")

    @staticmethod
    def _load_registry(path: Path, key: str) -> dict[str, str]:
        """YAML 레지스트리를 읽어 `{id: path}` 사전으로 변환한다.

        형식 검증을 엄격히 수행해 잘못된 레지스트리로 서버가 실행되지 않도록 한다.
        """
        if not path.exists():
            raise RegistryError(f"registry file not found: {path}")

        payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = payload.get(key)
        if not isinstance(entries, list):
            raise RegistryError(f"registry key '{key}' must be a list in {path}")

        out: dict[str, str] = {}
        for item in entries:
            if not isinstance(item, dict):
                raise RegistryError(f"invalid registry entry in {path}: {item}")

            item_id = item.get("id")
            item_path = item.get("path")
            if not isinstance(item_id, str) or not isinstance(item_path, str):
                raise RegistryError(f"registry entries must have string id/path in {path}")

            # 동일 ID가 중복되면 마지막 값으로 덮어쓴다. 운영에서는 중복 금지를 권장한다.
            out[item_id] = item_path

        return out

    def resolve_playbook(self, playbook_id: str) -> str:
        """playbook ID를 실제 파일 경로로 변환한다."""
        if playbook_id not in self._playbooks:
            raise RegistryError(f"unknown playbook_id: {playbook_id}")
        return self._playbooks[playbook_id]

    def resolve_inventory(self, inventory_id: str) -> str:
        """inventory ID를 실제 파일 경로로 변환한다."""
        if inventory_id not in self._inventories:
            raise RegistryError(f"unknown inventory_id: {inventory_id}")
        return self._inventories[inventory_id]

    def list_playbooks(self) -> dict[str, str]:
        """등록된 playbook 목록(ID -> path)을 반환한다."""
        return dict(self._playbooks)

    def list_inventories(self) -> dict[str, str]:
        """등록된 inventory 목록(ID -> path)을 반환한다."""
        return dict(self._inventories)
