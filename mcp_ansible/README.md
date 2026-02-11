# mcp_ansible

Ansible MCP server minimal implementation (MCP tool server over JSON-RPC via stdio).

## Project structure

- `mcp_ansible/main.py`: stdio entrypoint
- `mcp_ansible/mcp_router.py`: MCP server creation and tool registration wiring
- `mcp_ansible/tools.py`: MCP tools (`check`/`apply`) and registry-only validation path
- `mcp_ansible/registry_loader.py`: YAML registry loader and ID resolver
- `mcp_ansible/runner_wrapper.py`: `ansible-runner` execution wrapper + result shaping
- `mcp_ansible/schemas.py`: structured response dataclasses
- `mcp_ansible/logging_config.py`: stderr logging setup
- `mcp_ansible/configs/registry_playbooks.yaml`: allow-list for playbooks
- `mcp_ansible/configs/registry_inventories.yaml`: allow-list for inventories

## Install

```bash
pip install -e .
```

or

```bash
uv sync
```

## Run (stdio MCP)

```bash
python -m mcp_ansible.main
```

or

```bash
ansible-mcp
```

## Exposed tools

- `list_registered_playbooks`
- `list_registered_inventories`
- `run_playbook_check` (default safe mode: `--check`)
- `run_playbook_apply` (real apply mode)

## Tool input rules

- Only `playbook_id` and `inventory_id` are accepted.
- Direct filesystem paths are not accepted from tool inputs.
- IDs must exist in registry YAML files.

## Result schema

Each run returns structured JSON:

- `run_id`: unique execution id
- `status`: ansible-runner status
- `rc`: process return code
- `host_summary`: per-host `ok/changed/failed/unreachable`
- `failures`: array of failure/unreachable events
- `artifact_dir`: run artifact directory path

## Artifacts path

Default run artifacts root:

- `/var/lib/ansible-mcp/runs/<run_id>/`

Override with env var:

- `ANSIBLE_MCP_RUNS_DIR`

## Environment variables

- `ANSIBLE_MCP_RUNS_DIR` (optional): artifact root override
- `ANSIBLE_MCP_LOG_LEVEL` (optional, default `INFO`)

## Security notes

- Keep registry files writable only by trusted admins.
- Register only vetted playbooks/inventories.
- Prefer `run_playbook_check` first; use apply only after review.
- Enforce OS-level permissions so `/var/lib/ansible-mcp/runs` is not world-writable.
- If playbooks require secrets, use Ansible Vault or external secret manager.
