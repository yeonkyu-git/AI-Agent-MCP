from __future__ import annotations

import os
import sys
import shlex
import logging
import json
from dataclasses import dataclass
from typing import Dict, Optional, List, Any

import paramiko
from mcp.server.fastmcp import FastMCP

# ----- Logging: stderr only -----
logger = logging.getLogger("ssh-logs-mcp")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(_handler)

mcp = FastMCP("ssh-logs-mcp")

# ----- Load env file (optional) -----
SSH_ENV_FILE = os.environ.get("SSH_ENV_FILE", ".env.mcp_ssh")
_base_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = SSH_ENV_FILE
if _env_path and not os.path.isabs(_env_path):
    _env_path = os.path.join(_base_dir, _env_path)

if _env_path and os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        logger.warning(f"Failed to read env file: {e}")

# ----- SSH config (env) -----
SSH_USER = os.environ.get("SSH_USER", "userapp")
SSH_PASS = os.environ.get("SSH_PASS", "")
SSH_PORT = int(os.environ.get("SSH_PORT", "22"))
SSH_TIMEOUT_SEC = int(os.environ.get("SSH_TIMEOUT_SEC", "10"))

# If sudo password differs from SSH password, set SUDO_PASS.
SUDO_PASS = os.environ.get("SUDO_PASS", "")

# ----- Allowlist -----
RAW_ALLOWLIST = os.environ.get("SSH_ALLOWLIST", "").strip()

@dataclass(frozen=True)
class Server:
    key: str
    host: str
    name: str


def _parse_allowlist(raw: str) -> Dict[str, Server]:
    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError(f"Invalid SSH_ALLOWLIST JSON: {e}")

    if not isinstance(data, list):
        raise ValueError("SSH_ALLOWLIST must be a JSON array")

    out: Dict[str, Server] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip().lower()
        host = str(item.get("host", "")).strip()
        name = str(item.get("name", "")).strip() or key
        if not key or not host:
            continue
        out[key] = Server(key=key, host=host, name=name)
    return out


ALLOWLIST: Dict[str, Server] = _parse_allowlist(RAW_ALLOWLIST)


def _require_passwords() -> None:
    if not SSH_PASS:
        raise ValueError("SSH_PASS is not set")


def _get_server(server_key: str) -> Server:
    key = server_key.strip().lower()
    if key in ALLOWLIST:
        return ALLOWLIST[key]
    # allow lookup by host
    for s in ALLOWLIST.values():
        if s.host == server_key:
            return s
    raise ValueError(f"Unknown server: {server_key}")


def _ssh_exec(host: str, command: str) -> Dict[str, Any]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=SSH_PORT,
        username=SSH_USER,
        password=SSH_PASS,
        timeout=SSH_TIMEOUT_SEC,
        banner_timeout=SSH_TIMEOUT_SEC,
        auth_timeout=SSH_TIMEOUT_SEC,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        stdin, stdout, stderr = client.exec_command(command, get_pty=True)
        # sudo password handling
        if command.startswith("sudo -S "):
            pw = SUDO_PASS if SUDO_PASS else SSH_PASS
            stdin.write(pw + "\n")
            stdin.flush()

        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return {"stdout": out, "stderr": err}
    finally:
        client.close()


def _q(value: str) -> str:
    return shlex.quote(value)


def _build_tail(path: str, lines: int) -> str:
    return f"sudo -S tail -n {int(lines)} {_q(path)}"


def _build_head(path: str, lines: int) -> str:
    return f"sudo -S head -n {int(lines)} {_q(path)}"


def _build_grep(path: str, pattern: str, lines: int, ignore_case: bool) -> str:
    flag = "-i " if ignore_case else ""
    # Use grep + tail to cap output
    return f"sudo -S sh -lc {_q(f'grep {flag}{shlex.quote(pattern)} {shlex.quote(path)} | tail -n {int(lines)}')}"


def _build_range(
    path: str,
    since: Optional[str],
    until: Optional[str],
    lines: int,
) -> str:
    # Simple awk range filtering; expects ISO-like prefix in logs.
    # User must provide formats that exist in the file.
    conds: List[str] = []
    if since:
        conds.append(f'$0 >= "{since}"')
    if until:
        conds.append(f'$0 <= "{until}"')
    if not conds:
        return _build_tail(path, lines)
    awk_cond = " && ".join(conds)
    inner = f"awk '{awk_cond}' {shlex.quote(path)} | tail -n {int(lines)}"
    return f"sudo -S sh -lc {_q(inner)}"


@mcp.tool()
def list_servers() -> Dict[str, Any]:
    """Return allowlist servers."""
    return {
        "raw_allowlist": RAW_ALLOWLIST,
        "servers": [
            {"key": s.key, "host": s.host, "name": s.name} for s in ALLOWLIST.values()
        ]
    }


@mcp.tool()
def tail_log(server: str, path: str, lines: int = 100) -> Dict[str, Any]:
    """Tail a log file."""
    _require_passwords()
    s = _get_server(server)
    cmd = _build_tail(path, lines)
    res = _ssh_exec(s.host, cmd)
    return {"server": s.key, "host": s.host, "path": path, "lines": lines, **res}


@mcp.tool()
def head_log(server: str, path: str, lines: int = 100) -> Dict[str, Any]:
    """Head a log file."""
    _require_passwords()
    s = _get_server(server)
    cmd = _build_head(path, lines)
    res = _ssh_exec(s.host, cmd)
    return {"server": s.key, "host": s.host, "path": path, "lines": lines, **res}


@mcp.tool()
def grep_log(
    server: str,
    path: str,
    pattern: str,
    lines: int = 100,
    ignore_case: bool = True,
) -> Dict[str, Any]:
    """Grep a log file and return last N matching lines."""
    _require_passwords()
    s = _get_server(server)
    cmd = _build_grep(path, pattern, lines, ignore_case)
    res = _ssh_exec(s.host, cmd)
    return {
        "server": s.key,
        "host": s.host,
        "path": path,
        "pattern": pattern,
        "lines": lines,
        "ignore_case": ignore_case,
        **res,
    }


@mcp.tool()
def range_log(
    server: str,
    path: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
    lines: int = 100,
) -> Dict[str, Any]:
    """Filter by text range (simple lexicographic compare)."""
    _require_passwords()
    s = _get_server(server)
    cmd = _build_range(path, since, until, lines)
    res = _ssh_exec(s.host, cmd)
    return {
        "server": s.key,
        "host": s.host,
        "path": path,
        "since": since,
        "until": until,
        "lines": lines,
        **res,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
