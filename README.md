# MCP Tools (Prometheus/SSH) 🚀

이 저장소는 **Prometheus 기반 모니터링을 MCP 도구로 제공**하는 프로젝트입니다.  
운영자가 자연어로 질문하면, 지정된 체크/PromQL을 실행하고 요약 결과를 반환합니다.  

---

## ✨ 주요 기능

- 🔎 **사전 정의된 체크 실행** (`run_check`, `run_all_checks`)
- 🧠 **사용자 PromQL 실행** (`run_promql`)
- ✅ **AI 생성 PromQL 승인 흐름** (`run_generated_promql`)
- 🧭 **환경 목록 조회** (`list_environments`)
- 🖥️ **서버 목록 조회** (`list_servers`, up + server_name 기반)
- 🧩 **프로세스 그룹 목록 조회** (`list_process_groups`)
- 📊 **프로세스/DB/네트워크/소켓 상태** 체크 포함

---

## 🧱 사전 준비 (Windows 기준)

1. **Python 3.12+ 설치**
2. **uv 설치**
3. **Node.js + npm 설치** (Codex CLI 필요 시)

확인:
```powershell
python --version
uv --version
node -v
npm -v
```

---

## 📦 설치

```powershell
# 프로젝트 루트
uv sync
```

---

## ⚙️ 환경 변수 설정

### 1) `.env` 파일 사용 (권장)
`.env`는 자동 로드됩니다.

예시: `.env` (실제 운영 값 입력)
```env
# Prometheus MCP
PROM_ENV_URLS={"prod":"http://<prom-host>:9090","dev_test":"http://<prom-host>:9090","dr":"http://<prom-host>:9090"}
# PROM_URL="http://<prom-host>:9090"  # optional default
# PROM_BEARER_TOKEN=""                # optional
# PROM_TIMEOUT_SEC="15"

# SSH MCP credentials
SSH_USER=""
SSH_PASS=""
SUDO_PASS=""
SSH_ALLOWLIST=[]
```

✅ `.env`는 `.gitignore`에 포함되어 커밋되지 않습니다.

### 2) 환경변수 직접 설정
```powershell
$env:PROM_ENV_URLS='{"prod":"http://10.0.0.1:9090"}'
```

---

## ▶️ 실행

```powershell
uv run python mcp_prometheus.py
```

---

## 🛠️ 제공 도구 목록

### 기본
- `list_environments()`
- `list_checks()`
- `run_check(...)`
- `run_all_checks(...)`

### PromQL
- `run_promql(...)`  
- `run_generated_promql(...)`  ← **승인 필수**

### 상태/목록
- `list_servers(...)`  ← **up + server_name 기준**
- `list_process_groups(...)`

---

## ✅ 승인 흐름 (AI 생성 PromQL)

`run_generated_promql`은 반드시 사용자 승인 후 실행됩니다.

1) 승인 요청
```json
{"question":"...","promql":"...","approved":false}
```

2) 승인 후 실행
```json
{"question":"...","promql":"...","approved":true}
```

---

## 📌 체크 예시 질문

- “최근 15분 동안 CPU 사용률이 가장 높은 서버는?”
- “PostgreSQL QPS가 급증한 DB가 있나?”
- “TCP TIME_WAIT 소켓이 많은 서버는?”
- “프로세스 그룹별 메모리 사용량 Top 5 보여줘.”

---

## 🧯 트러블슈팅

### 1) 환경 목록이 비어 있음
- `.env` 로딩 실패 or `PROM_ENV_URLS` 미설정
- 해결: `.env` 설정 후 재시작

### 2) `run_check` 에러
- PromQL 라벨/메트릭명이 실제 환경과 다를 수 있음
- 필요한 메트릭명을 알려주면 바로 수정 가능

---

## 🔒 보안 권장 사항

- `.env`, `.env.mcp_ssh`는 **절대 커밋하지 마세요**
- 내부 IP/자격증명은 `.env.example`만 공유

---

## 📄 라이선스

필요 시 추가하세요.
