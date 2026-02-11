from __future__ import annotations

"""MCP 응답 정형화 스키마(dataclass) 모음.

`ansible-runner`의 결과 구조는 그대로 노출하면 소비자가 다루기 어렵다.
따라서 서버에서 필요한 정보만 추려 고정 JSON 형태로 변환하기 위해
명시적 데이터 클래스를 사용한다.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HostSummary:
    """호스트 단위 실행 집계 값.

    Attributes:
        ok: 성공 task 수.
        changed: 변경 발생 task 수.
        failed: 실패 task 수.
        unreachable: 접속 불가(unreachable) 횟수.
    """

    ok: int = 0
    changed: int = 0
    failed: int = 0
    unreachable: int = 0


@dataclass
class FailureItem:
    """실패/접속불가 이벤트 1건을 표현한다.

    Attributes:
        host: 문제가 발생한 대상 호스트.
        task: 실패한 태스크 이름.
        message: runner 이벤트에서 추출한 실패 메시지.
        event: 이벤트 타입(`runner_on_failed` 등).
    """

    host: str
    task: str
    message: str
    event: str


@dataclass
class RunResult:
    """MCP tool 응답의 최상위 결과 스키마.

    Attributes:
        run_id: 실행 단위 UUID.
        status: ansible-runner 상태 문자열(successful/failed 등).
        rc: 프로세스 리턴 코드.
        host_summary: 호스트별 집계 결과.
        failures: 실패 이벤트 목록.
        artifact_dir: 해당 run의 artifact 저장 디렉터리.
    """

    run_id: str
    status: str
    rc: int
    host_summary: dict[str, HostSummary] = field(default_factory=dict)
    failures: list[FailureItem] = field(default_factory=list)
    artifact_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        """dataclass 구조를 JSON 직렬화 가능한 dict로 변환한다."""
        host_summary = {host: asdict(summary) for host, summary in self.host_summary.items()}
        failures = [asdict(item) for item in self.failures]
        return {
            "run_id": self.run_id,
            "status": self.status,
            "rc": self.rc,
            "host_summary": host_summary,
            "failures": failures,
            "artifact_dir": self.artifact_dir,
        }
