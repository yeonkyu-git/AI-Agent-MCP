# server.py
from __future__ import annotations

import os
import sys
import time
import math
import logging
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ----- Logging: stderr only (stdout is reserved for MCP protocol) -----
logger = logging.getLogger("prom-mcp")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(_handler)

mcp = FastMCP("prometheus-health-mcp")

# Load .env if present
load_dotenv()

DEFAULT_PROM_URL = os.environ.get("PROM_URL", "").rstrip("/")
PROM_BEARER_TOKEN = os.environ.get("PROM_BEARER_TOKEN", "")
HTTP_TIMEOUT_SEC = float(os.environ.get("PROM_TIMEOUT_SEC", "15"))
ALERT_WARN_PCT = float(os.environ.get("ALERT_WARN_PCT", "85"))
ALERT_CRIT_PCT = float(os.environ.get("ALERT_CRIT_PCT", "95"))
ALERT_SUSTAIN_MINUTES = int(os.environ.get("ALERT_SUSTAIN_MINUTES", "5"))

ENV_URLS: Dict[str, str] = {}
_ENV_URLS_RAW = os.environ.get("PROM_ENV_URLS", "").strip()
if _ENV_URLS_RAW:
    try:
        _parsed = json.loads(_ENV_URLS_RAW)
        if isinstance(_parsed, dict):
            ENV_URLS = {str(k): str(v) for k, v in _parsed.items()}
        else:
            logger.warning("PROM_ENV_URLS must be a JSON object; ignoring.")
    except Exception:
        logger.warning("Failed to parse PROM_ENV_URLS; ignoring.")
else:
    logger.warning("PROM_ENV_URLS is not set; ENV_URLS is empty.")

@dataclass(frozen=True)
class Check:
    id: str
    name: str
    description: str
    promql: str
    kind: str = "range"

# ----- Allowlist checks -----
CHECKS: Dict[str, Check] = {
    "cpu_avg_pct": Check(
        id="cpu_avg_pct",
        name="1. CPU 평균 사용률 (%)",
        description="전체 인스턴스의 CPU 사용률 추이",
        promql='100 - (avg by (instance,server_name) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
    ),
    "cpu_peak_pct": Check(
        id="cpu_peak_pct",
        name="2. CPU 최대 부하 (Peak, window max)",
        description="선택한 기간(window)의 CPU 사용률 피크(최대값)",
        promql='max_over_time((100 - (avg by (instance,server_name) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100))[{range}:])',
    ),
    "mem_used_pct": Check(
        id="mem_used_pct",
        name="3. 메모리 사용률 (%)",
        description="실질적인 메모리 사용량",
        promql="100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
    ),
    "mem_swap_used_pct": Check(
        id="mem_swap_used_pct",
        name="4. Swap 사용률 (%)",
        description="스왑 사용률",
        promql="100 * (1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes)",
    ),
    "disk_used_top5_pct": Check(
        id="disk_used_top5_pct",
        name="5. 디스크 부족 경고 (Top 5 사용률)",
        description="tmpfs/overlay 제외, 사용률 상위 5개",
        promql='topk(5, 100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})))',
    ),
    "disk_inodes_used_pct": Check(
        id="disk_inodes_used_pct",
        name="6. 디스크 Inodes 사용률 (%)",
        description="파일시스템 inode 사용률",
        promql='100 * (1 - (node_filesystem_files_free{fstype!~"tmpfs|overlay"} / node_filesystem_files{fstype!~"tmpfs|overlay"}))',
    ),
    "fs_readonly": Check(
        id="fs_readonly",
        name="7. Filesystem Readonly",
        description="읽기 전용 파일시스템 (1=readonly)",
        promql='max by (instance,server_name,device,mountpoint,fstype) (node_filesystem_readonly{fstype!~"tmpfs|overlay"})',
    ),
    "load15_avg": Check(
        id="load15_avg",
        name="8. 시스템 부하 (Load 15m)",
        description="15분 시스템 부하 평균",
        promql="avg by (instance, server_name) (node_load15)",
    ),
    "up": Check(
        id="up",
        name="9. 서버 생존 여부 (Up)",
        description="서버 생존 여부 (1=Up, 0=Down)",
        promql="up",
    ),
    "cpu_iowait_pct": Check(
        id="cpu_iowait_pct",
        name="10. CPU IOWAIT (%)",
        description="CPU iowait 비율",
        promql='avg by (instance,server_name) (rate(node_cpu_seconds_total{mode="iowait"}[5m])) * 100',
    ),
    "net_in_bytes": Check(
        id="net_in_bytes",
        name="11. 네트워크 트래픽 유입 (Inbound)",
        description="네트워크 유입 트래픽 (bytes/sec)",
        promql='sum by (instance,server_name) (rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*"}[5m]))',
    ),
    "net_out_bytes": Check(
        id="net_out_bytes",
        name="12. 네트워크 트래픽 유출 (Outbound)",
        description="네트워크 유출 트래픽 (bytes/sec)",
        promql='sum by (instance,server_name) (rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*"}[5m]))',
    ),
    "net_errs_per_sec": Check(
        id="net_errs_per_sec",
        name="13. 네트워크 오류 (per sec)",
        description="네트워크 RX/TX 오류 (초당)",
        promql='sum by (instance,server_name) (rate(node_network_receive_errs_total{device!~"lo|docker.*|veth.*"}[5m]) + rate(node_network_transmit_errs_total{device!~"lo|docker.*|veth.*"}[5m]))',
    ),
    "tcp_retrans_per_sec": Check(
        id="tcp_retrans_per_sec",
        name="14. TCP 재전송 (per sec)",
        description="TCP 재전송 (초당)",
        promql='sum by (instance,server_name) (rate(node_netstat_Tcp_RetransSegs[5m]))',
    ),
    "disk_io_busy_pct": Check(
        id="disk_io_busy_pct",
        name="15. 디스크 I/O 부하 (busy %)",
        description="디스크가 바쁜 정도(시간 비율)",
        promql="avg by (instance,server_name) (rate(node_disk_io_time_seconds_total[5m])) * 100",
    ),
    "tcp_established": Check(
        id="tcp_established",
        name="15. TCP ESTABLISHED 소켓 수",
        description="ESTABLISHED 상태의 TCP 소켓 개수",
        promql='sum by (instance,server_name) (node_netstat_Tcp_CurrEstab)',
    ),
    "tcp_time_wait": Check(
        id="tcp_time_wait",
        name="16. TCP TIME_WAIT 소켓 수",
        description="TIME_WAIT 상태의 TCP 소켓 개수",
        promql='sum by (instance,server_name) (node_sockstat_TCP_tw)',
    ),
    "tcp_inuse": Check(
        id="tcp_inuse",
        name="17. TCP inuse 소켓 수",
        description="사용 중인 TCP 소켓 개수",
        promql='sum by (instance,server_name) (node_sockstat_TCP_inuse)',
    ),
    "tcp_orphan": Check(
        id="tcp_orphan",
        name="18. TCP orphan 소켓 수",
        description="orphan TCP 소켓 개수",
        promql='sum by (instance,server_name) (node_sockstat_TCP_orphan)',
    ),
    "proc_cpu_pct": Check(
        id="proc_cpu_pct",
        name="16. 프로세스 CPU 사용률 (%)",
        description="프로세스 그룹별 CPU 사용률",
        promql='sum by (instance,server_name,groupname) (rate(namedprocess_namegroup_cpu_seconds_total{job="process_monitoring"}[5m])) * 100',
    ),
    "proc_mem_bytes": Check(
        id="proc_mem_bytes",
        name="17. 프로세스 메모리 사용량 (bytes)",
        description="프로세스 그룹별 메모리 사용량 (bytes)",
        promql='max by (instance,server_name,groupname) (namedprocess_namegroup_memory_bytes{job="process_monitoring"})',
    ),
    "proc_count": Check(
        id="proc_count",
        name="18. 프로세스 개수",
        description="프로세스 그룹별 개수",
        promql='max by (instance,server_name,groupname) (namedprocess_namegroup_num_procs{job="process_monitoring"})',
    ),
    "pg_up": Check(
        id="pg_up",
        name="19. PostgreSQL Up",
        description="PostgreSQL exporter 상태 (1=Up, 0=Down)",
        promql='up{job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"}',
    ),
    "pg_qps": Check(
        id="pg_qps",
        name="20. PostgreSQL QPS",
        description="PostgreSQL 트랜잭션 처리량(초당)",
        promql='sum by (instance,server_name,datname) (rate(pg_stat_database_xact_commit{job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"}[5m]) + rate(pg_stat_database_xact_rollback{job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"}[5m]))',
    ),
    "pg_cache_hit_pct": Check(
        id="pg_cache_hit_pct",
        name="21. PostgreSQL Cache Hit (%)",
        description="PostgreSQL 버퍼 캐시 히트 비율",
        promql='100 * sum by (instance,server_name,datname) (rate(pg_stat_database_blks_hit{job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"}[5m])) / sum by (instance,server_name,datname) (rate(pg_stat_database_blks_hit{job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"}[5m]) + rate(pg_stat_database_blks_read{job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"}[5m]))',
    ),
    "pg_active_conn": Check(
        id="pg_active_conn",
        name="22. PostgreSQL Active Connections",
        description="PostgreSQL 활성 연결 수",
        promql='sum by (instance,server_name,datname) (pg_stat_activity_count{state="active",job=~"PROD DB PostgreSQL|TEST DB PostgreSQL|DEV DB PostgreSQL"})',
    ),
}

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _to_unix(dt: datetime) -> float:
    return dt.timestamp()

def _parse_step(step: str) -> str:
    step = step.strip()
    if not step:
        return "5m"
    return step

def _step_to_seconds(step: str) -> int:
    s = step.strip().lower()
    if not s:
        return 300
    unit = s[-1]
    try:
        val = int(s[:-1])
    except Exception:
        return 300
    if unit == "s":
        return val
    if unit == "m":
        return val * 60
    if unit == "h":
        return val * 3600
    if unit == "d":
        return val * 86400
    return 300

def _parse_iso_utc(value: str) -> datetime:
    s = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _format_range(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total <= 0:
        return "0s"
    if total % 86400 == 0:
        return f"{total // 86400}d"
    if total % 3600 == 0:
        return f"{total // 3600}h"
    if total % 60 == 0:
        return f"{total // 60}m"
    return f"{total}s"

def _resolve_time_range(
    *,
    hours: Optional[int],
    minutes: Optional[int],
    days: Optional[int],
    start_time_utc_iso: Optional[str],
    end_time_utc_iso: Optional[str],
    end_offset_minutes: Optional[int],
    end_offset_hours: Optional[int],
    end_offset_days: Optional[int],
) -> Tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)

    if end_time_utc_iso:
        end = _parse_iso_utc(end_time_utc_iso)
    elif end_offset_minutes or end_offset_hours or end_offset_days:
        delta = timedelta(
            minutes=int(end_offset_minutes or 0),
            hours=int(end_offset_hours or 0),
            days=int(end_offset_days or 0),
        )
        end = now - delta
    else:
        end = now

    if start_time_utc_iso:
        start = _parse_iso_utc(start_time_utc_iso)
    else:
        if minutes or days:
            hours_val = int(hours) if hours is not None else 0
            days_val = int(days) if days is not None else 0
            delta = timedelta(
                minutes=int(minutes or 0),
                hours=hours_val,
                days=days_val,
            )
        else:
            delta = timedelta(hours=int(hours or 24))
        start = end - delta

    if start > end:
        raise ValueError("start_time must be <= end_time")
    return start, end

def _render_promql(c: Check, range_str: str) -> str:
    if "{range}" in c.promql:
        return c.promql.replace("{range}", range_str)
    return c.promql

def _apply_target_filter(
    promql: str,
    *,
    server_name: Optional[str],
    instance: Optional[str],
) -> str:
    if not server_name and not instance:
        return promql

    matchers: List[str] = []
    on_labels: List[str] = []
    if instance:
        matchers.append(f'instance="{instance}"')
        on_labels.append("instance")
    if server_name:
        matchers.append(f'server_name="{server_name}"')
        on_labels.append("server_name")

    matcher_str = ",".join(matchers)
    on_str = ",".join(on_labels)
    return f"({promql}) and on ({on_str}) up{{{matcher_str}}}"

def _prom_headers() -> Dict[str, str]:
    h = {"Accept": "application/json"}
    if PROM_BEARER_TOKEN:
        h["Authorization"] = f"Bearer {PROM_BEARER_TOKEN}"
    return h

def _normalize_env(value: str) -> str:
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    if v in ("prod", "production", "운영"):
        return "prod"
    if v in ("dev", "develop", "development", "개발"):
        return "dev"
    if v in ("test", "testing", "qa", "테스트"):
        return "test"
    if v in ("dr", "disaster_recovery", "재해복구"):
        return "dr"
    if v in ("dev_test", "devtest", "dev_and_test"):
        return "dev_test"
    return v

def _resolve_prom_url(environment: Optional[str], env_hint: Optional[str]) -> Tuple[str, str]:
    if environment:
        key = _normalize_env(environment)
        if key in ENV_URLS:
            return key, ENV_URLS[key]
        raise ValueError(f"Unknown environment: {environment}")

    if env_hint:
        key = _normalize_env(env_hint)
        if key in ENV_URLS:
            return key, ENV_URLS[key]

    if DEFAULT_PROM_URL:
        return "default", DEFAULT_PROM_URL

    raise ValueError("No environment selected and PROM_URL is not set")

def _prom_query_range(prom_url: str, query: str, start: datetime, end: datetime, step: str) -> Dict[str, Any]:
    if not prom_url:
        raise ValueError("prom_url is empty")

    url = f"{prom_url.rstrip('/')}/api/v1/query_range"
    params = {
        "query": query,
        "start": _to_unix(start),
        "end": _to_unix(end),
        "step": step,
    }
    r = requests.get(url, params=params, headers=_prom_headers(), timeout=HTTP_TIMEOUT_SEC)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {data}")
    return data

def _prom_label_values(prom_url: str, label: str, match: Optional[str] = None) -> List[str]:
    if not prom_url:
        raise ValueError("prom_url is empty")

    url = f"{prom_url.rstrip('/')}/api/v1/label/{label}/values"
    params: Dict[str, Any] = {}
    if match:
        params["match[]"] = match
    r = requests.get(url, params=params, headers=_prom_headers(), timeout=HTTP_TIMEOUT_SEC)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {data}")
    return data.get("data", [])

def _stats_from_values(values: List[List[Any]]) -> Dict[str, Any]:
    nums: List[float] = []
    last_ts: Optional[float] = None
    last_val: Optional[float] = None

    for ts, v in values:
        try:
            fv = float(v)
            if math.isfinite(fv):
                nums.append(fv)
                last_ts = float(ts)
                last_val = fv
        except Exception:
            continue

    if not nums:
        return {"count": 0}

    return {
        "count": len(nums),
        "min": min(nums),
        "max": max(nums),
        "avg": sum(nums) / len(nums),
        "last": last_val,
        "last_ts": last_ts,
    }

def _max_sustain_duration(
    values: List[List[Any]],
    *,
    threshold: float,
    step_seconds: int,
) -> float:
    max_dur = 0.0
    active_start: Optional[float] = None
    last_ts: Optional[float] = None

    gap_reset = max(1, int(step_seconds * 1.5))

    for ts, v in values:
        try:
            t = float(ts)
            fv = float(v)
            if not math.isfinite(fv):
                raise ValueError()
        except Exception:
            last_ts = None
            active_start = None
            continue

        if last_ts is not None and (t - last_ts) > gap_reset:
            active_start = None

        if fv >= threshold:
            if active_start is None:
                active_start = t
            dur = t - active_start
            if dur > max_dur:
                max_dur = dur
        else:
            active_start = None

        last_ts = t

    return max_dur

def _summarize_matrix(
    result_matrix: List[Dict[str, Any]],
    include_samples: bool,
    *,
    alert_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for series in result_matrix:
        metric = series.get("metric", {})
        values = series.get("values", [])
        summary = _stats_from_values(values)
        if alert_config and summary.get("count", 0) > 0:
            step_seconds = int(alert_config["step_seconds"])
            sustain_seconds = int(alert_config["sustain_seconds"])
            warn_pct = float(alert_config["warn_pct"])
            crit_pct = float(alert_config["crit_pct"])
            warn_max = _max_sustain_duration(values, threshold=warn_pct, step_seconds=step_seconds)
            crit_max = _max_sustain_duration(values, threshold=crit_pct, step_seconds=step_seconds)
            summary["sustain"] = {
                "warning": {
                    "threshold_pct": warn_pct,
                    "min_duration_sec": sustain_seconds,
                    "max_duration_sec": warn_max,
                    "breached": warn_max >= sustain_seconds,
                },
                "critical": {
                    "threshold_pct": crit_pct,
                    "min_duration_sec": sustain_seconds,
                    "max_duration_sec": crit_max,
                    "breached": crit_max >= sustain_seconds,
                },
            }
        item = {"metric": metric, "summary": summary}
        if include_samples:
            item["values"] = values
        out.append(item)
    return out

def _should_apply_alerts(c: Optional[Check]) -> bool:
    if not c:
        return False
    if "%" in c.name:
        return True
    return c.id.endswith("_pct")

@mcp.tool()
def list_checks() -> Dict[str, Any]:
    """서버가 제공하는 점검 체크(allowlist)를 반환"""
    checks = []
    for c in CHECKS.values():
        checks.append({"id": c.id, "name": c.name, "description": c.description})
    return {"checks": checks}

@mcp.tool()
def list_environments() -> Dict[str, Any]:
    """사용 가능한 환경 목록을 반환"""
    envs = [{"key": k, "prom_url": v} for k, v in ENV_URLS.items()]
    return {"environments": envs}

@mcp.tool()
def list_servers(
    environment: Optional[str] = None,
    env_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    up 메트릭 기반으로 모니터링 가능한 서버 목록 반환.
    """
    env_key, prom_url = _resolve_prom_url(environment, env_hint)
    result = _prom_query_range(
        prom_url,
        'up{server_name!=""}',
        start=datetime.now(timezone.utc) - timedelta(minutes=10),
        end=datetime.now(timezone.utc),
        step="5m",
    )
    series = result.get("data", {}).get("result", [])
    servers = []
    for s in series:
        m = s.get("metric", {})
        server_name = m.get("server_name")
        if not server_name:
            continue
        servers.append({
            "instance": m.get("instance"),
            "job": m.get("job"),
            "server_name": server_name,
        })
    # remove duplicates
    uniq = []
    seen = set()
    for s in servers:
        key = (s.get("instance"), s.get("job"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return {"environment": env_key, "prom_url": prom_url, "servers": uniq}

@mcp.tool()
def list_process_groups(
    environment: Optional[str] = None,
    env_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    process_monitoring job 기준으로 모니터링 중인 프로세스 그룹(groupname) 목록 반환.
    """
    env_key, prom_url = _resolve_prom_url(environment, env_hint)
    groups = _prom_label_values(
        prom_url,
        label="groupname",
        match='namedprocess_namegroup_cpu_seconds_total{job="process_monitoring"}',
    )
    groups = sorted(set([g for g in groups if g]))
    return {"environment": env_key, "prom_url": prom_url, "groups": groups}

@mcp.tool()
def run_check(
    check_id: str,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    days: Optional[int] = None,
    step: str = "5m",
    include_samples: bool = False,
    start_time_utc_iso: Optional[str] = None,
    end_time_utc_iso: Optional[str] = None,
    end_offset_minutes: Optional[int] = None,
    end_offset_hours: Optional[int] = None,
    end_offset_days: Optional[int] = None,
    server_name: Optional[str] = None,
    instance: Optional[str] = None,
    environment: Optional[str] = None,
    env_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    특정 체크를 query_range로 실행.
    - 기본: 최근 24h
    - minutes / hours / days: 기간 길이 지정
    - start_time_utc_iso / end_time_utc_iso: 기간 직접 지정
    - end_offset_*: end(now)에서 과거로 오프셋
    - server_name / instance: 특정 서버만 필터링
    """
    if check_id not in CHECKS:
        raise ValueError(f"Unknown check_id: {check_id}")

    c = CHECKS[check_id]
    step = _parse_step(step)
    env_key, prom_url = _resolve_prom_url(environment, env_hint)

    start, end = _resolve_time_range(
        hours=hours,
        minutes=minutes,
        days=days,
        start_time_utc_iso=start_time_utc_iso,
        end_time_utc_iso=end_time_utc_iso,
        end_offset_minutes=end_offset_minutes,
        end_offset_hours=end_offset_hours,
        end_offset_days=end_offset_days,
    )
    range_str = _format_range(end - start)
    promql = _render_promql(c, range_str)
    promql = _apply_target_filter(promql, server_name=server_name, instance=instance)

    alert_config = None
    if _should_apply_alerts(c):
        alert_config = {
            "warn_pct": ALERT_WARN_PCT,
            "crit_pct": ALERT_CRIT_PCT,
            "sustain_seconds": ALERT_SUSTAIN_MINUTES * 60,
            "step_seconds": _step_to_seconds(step),
        }

    t0 = time.time()
    data = _prom_query_range(prom_url, promql, start=start, end=end, step=step)
    elapsed_ms = int((time.time() - t0) * 1000)

    result = data.get("data", {}).get("result", [])
    summarized = _summarize_matrix(result, include_samples=include_samples, alert_config=alert_config)

    return {
        "check": {"id": c.id, "name": c.name, "description": c.description},
        "environment": env_key,
        "prom_url": prom_url,
        "filter": {"server_name": server_name, "instance": instance},
        "alert_config": alert_config,
        "range": {"start": _iso(start), "end": _iso(end), "step": step},
        "series_count": len(summarized),
        "elapsed_ms": elapsed_ms,
        "results": summarized,
    }

@mcp.tool()
def run_all_checks(
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    days: Optional[int] = None,
    step: str = "5m",
    include_samples: bool = False,
    start_time_utc_iso: Optional[str] = None,
    end_time_utc_iso: Optional[str] = None,
    end_offset_minutes: Optional[int] = None,
    end_offset_hours: Optional[int] = None,
    end_offset_days: Optional[int] = None,
    server_name: Optional[str] = None,
    instance: Optional[str] = None,
    environment: Optional[str] = None,
    env_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """모든 체크를 실행해서 한 번에 반환(기본은 요약만). server_name/instance로 필터 가능."""
    step = _parse_step(step)
    env_key, prom_url = _resolve_prom_url(environment, env_hint)
    start, end = _resolve_time_range(
        hours=hours,
        minutes=minutes,
        days=days,
        start_time_utc_iso=start_time_utc_iso,
        end_time_utc_iso=end_time_utc_iso,
        end_offset_minutes=end_offset_minutes,
        end_offset_hours=end_offset_hours,
        end_offset_days=end_offset_days,
    )
    range_str = _format_range(end - start)

    out: List[Dict[str, Any]] = []
    for check_id in CHECKS.keys():
        c = CHECKS[check_id]
        promql = _render_promql(c, range_str)
        promql = _apply_target_filter(promql, server_name=server_name, instance=instance)

        alert_config = None
        if _should_apply_alerts(c):
            alert_config = {
                "warn_pct": ALERT_WARN_PCT,
                "crit_pct": ALERT_CRIT_PCT,
                "sustain_seconds": ALERT_SUSTAIN_MINUTES * 60,
                "step_seconds": _step_to_seconds(step),
            }
        t0 = time.time()
        data = _prom_query_range(prom_url, promql, start=start, end=end, step=step)
        elapsed_ms = int((time.time() - t0) * 1000)

        result = data.get("data", {}).get("result", [])
        summarized = _summarize_matrix(result, include_samples=include_samples, alert_config=alert_config)

        out.append({
            "check": {"id": c.id, "name": c.name, "description": c.description},
            "series_count": len(summarized),
            "elapsed_ms": elapsed_ms,
            "alert_config": alert_config,
            "results": summarized,
        })

    return {
        "environment": env_key,
        "prom_url": prom_url,
        "filter": {"server_name": server_name, "instance": instance},
        "range": {"start": _iso(start), "end": _iso(end), "step": step},
        "checks": out,
    }

@mcp.tool()
def run_promql(
    promql: str,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    days: Optional[int] = None,
    step: str = "5m",
    include_samples: bool = False,
    start_time_utc_iso: Optional[str] = None,
    end_time_utc_iso: Optional[str] = None,
    end_offset_minutes: Optional[int] = None,
    end_offset_hours: Optional[int] = None,
    end_offset_days: Optional[int] = None,
    server_name: Optional[str] = None,
    instance: Optional[str] = None,
    environment: Optional[str] = None,
    env_hint: Optional[str] = None,
    alert_pct: bool = False,
) -> Dict[str, Any]:
    """
    사용자가 제공한 PromQL을 query_range로 실행.
    - 기본: 최근 24h
    - minutes / hours / days: 기간 길이 지정
    - start_time_utc_iso / end_time_utc_iso: 기간 직접 지정
    - end_offset_*: end(now)에서 과거로 오프셋
    - server_name / instance: 특정 서버만 필터링
    """
    if not promql or not promql.strip():
        raise ValueError("promql is required")

    step = _parse_step(step)
    env_key, prom_url = _resolve_prom_url(environment, env_hint)

    start, end = _resolve_time_range(
        hours=hours,
        minutes=minutes,
        days=days,
        start_time_utc_iso=start_time_utc_iso,
        end_time_utc_iso=end_time_utc_iso,
        end_offset_minutes=end_offset_minutes,
        end_offset_hours=end_offset_hours,
        end_offset_days=end_offset_days,
    )

    filtered_promql = _apply_target_filter(promql.strip(), server_name=server_name, instance=instance)

    alert_config = None
    if alert_pct:
        alert_config = {
            "warn_pct": ALERT_WARN_PCT,
            "crit_pct": ALERT_CRIT_PCT,
            "sustain_seconds": ALERT_SUSTAIN_MINUTES * 60,
            "step_seconds": _step_to_seconds(step),
        }

    t0 = time.time()
    data = _prom_query_range(prom_url, filtered_promql, start=start, end=end, step=step)
    elapsed_ms = int((time.time() - t0) * 1000)

    result = data.get("data", {}).get("result", [])
    summarized = _summarize_matrix(result, include_samples=include_samples, alert_config=alert_config)

    return {
        "promql": promql.strip(),
        "filter": {"server_name": server_name, "instance": instance},
        "alert_config": alert_config,
        "environment": env_key,
        "prom_url": prom_url,
        "range": {"start": _iso(start), "end": _iso(end), "step": step},
        "series_count": len(summarized),
        "elapsed_ms": elapsed_ms,
        "results": summarized,
    }

@mcp.tool()
def run_generated_promql(
    question: str,
    promql: str,
    approved: bool = False,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
    days: Optional[int] = None,
    step: str = "5m",
    include_samples: bool = False,
    start_time_utc_iso: Optional[str] = None,
    end_time_utc_iso: Optional[str] = None,
    end_offset_minutes: Optional[int] = None,
    end_offset_hours: Optional[int] = None,
    end_offset_days: Optional[int] = None,
    server_name: Optional[str] = None,
    instance: Optional[str] = None,
    environment: Optional[str] = None,
    env_hint: Optional[str] = None,
    alert_pct: bool = False,
) -> Dict[str, Any]:
    """
    AI가 생성한 PromQL 실행용 도구. 반드시 사용자의 승인(approved=True)이 필요함.
    승인 전에는 실행하지 않고 실행할 PromQL과 승인 요청 정보를 반환.
    server_name/instance로 특정 서버만 필터링 가능.
    """
    if not promql or not promql.strip():
        raise ValueError("promql is required")
    if not question or not question.strip():
        raise ValueError("question is required")

    if not approved:
        return {
            "approved": False,
            "question": question.strip(),
            "promql": promql.strip(),
            "message": "이 PromQL을 실행해도 될까요? 승인하려면 approved=True로 다시 호출해주세요.",
        }

    step = _parse_step(step)
    env_key, prom_url = _resolve_prom_url(environment, env_hint)

    start, end = _resolve_time_range(
        hours=hours,
        minutes=minutes,
        days=days,
        start_time_utc_iso=start_time_utc_iso,
        end_time_utc_iso=end_time_utc_iso,
        end_offset_minutes=end_offset_minutes,
        end_offset_hours=end_offset_hours,
        end_offset_days=end_offset_days,
    )

    filtered_promql = _apply_target_filter(promql.strip(), server_name=server_name, instance=instance)

    alert_config = None
    if alert_pct:
        alert_config = {
            "warn_pct": ALERT_WARN_PCT,
            "crit_pct": ALERT_CRIT_PCT,
            "sustain_seconds": ALERT_SUSTAIN_MINUTES * 60,
            "step_seconds": _step_to_seconds(step),
        }

    t0 = time.time()
    data = _prom_query_range(prom_url, filtered_promql, start=start, end=end, step=step)
    elapsed_ms = int((time.time() - t0) * 1000)

    result = data.get("data", {}).get("result", [])
    summarized = _summarize_matrix(result, include_samples=include_samples, alert_config=alert_config)

    return {
        "approved": True,
        "question": question.strip(),
        "promql": promql.strip(),
        "filter": {"server_name": server_name, "instance": instance},
        "alert_config": alert_config,
        "environment": env_key,
        "prom_url": prom_url,
        "range": {"start": _iso(start), "end": _iso(end), "step": step},
        "series_count": len(summarized),
        "elapsed_ms": elapsed_ms,
        "results": summarized,
    }

if __name__ == "__main__":
    mcp.run()
