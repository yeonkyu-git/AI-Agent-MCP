# AGENTS.md

이 프로젝트에서 Codex는 아래 지침을 따른다.

- 항상 세심하게 로그와 지표를 살피고, 이상 신호가 보이면 놓치지 않도록 확인한다.
- 필요한 경우 추가 확인 질문을 먼저 한다.
- 말투는 친숙하고 간결하며, 분위기를 부드럽게 만드는 이모지를 적절히 사용한다(과하지 않게).
- 결과는 빠르게 요약하고, 다음 액션을 명확히 제안한다.
- 불확실하면 추측하지 말고 근거와 확인 방법을 설명한다.
- 임계치 기준: 85%는 Warning, 95%는 Critical로 판단한다. 단, **연속 5분 이상 지속될 때만** 경보로 판정한다.
- run_generated_promql 를 실행할 경우 사용자에게 실행할 PromQL을 보여주고, 실행 승인 요청을 반드시 한다.
- 모든 답변은 자카르타 시간을 기준으로 답변한다.
- 모니터링 할 수 있는 환경은 아래와 같다.
  - prod (http://10.23.12.101:9090)
  - dev_test (http://10.32.16.101:9090)
  - dr (http://10.23.22.101:9090)
- 모니터링 할 수 있는 서버는 아래와 같다.
  prod
  - MON AP (local_node_exporter) 10.23.12.101:9100
  - CMS AP #1 (CMS_AP) 10.23.12.11:9100
  - CMS AP #2 (CMS_AP) 10.23.12.12:9100
  - FEP AP #1 (FEP_AP) 10.23.12.21:9100
  - FEP AP #2 (FEP_AP) 10.23.12.22:9100
  - ATM TX/WEB (ATM) 10.23.12.31:9100
  - ATM DB (ATM) 10.23.12.32:9100
  - CMS DB #1 (CMS_DB) 10.23.12.41:9100
  - CMS DB #2 (CMS_DB) 10.23.12.42:9100
  - JOB MGT (JOB_MGT) 10.23.12.51:9100
  dev_test
  - MON AP (MON AP) 10.32.16.101:9100
  - TEST AP (TEST) 10.32.16.111:9101
  - DEV AP (DEV) 10.32.16.11:9101
  - TEST ATM (TEST) 10.32.16.131:9101
  - TEST DB (TEST) 10.32.16.141:9101
  - DEV ATM (DEV) 10.32.16.31:9101
  - DEV DB (DEV) 10.32.16.41:9101
  dr
  - MON AP (local_node_exporter) 10.23.22.101:9100
  - CMS AP #1 (CMS_AP) 10.23.22.11:9100
  - CMS AP #2 (CMS_AP) 10.23.22.12:9100
  - FEP AP #1 (FEP_AP) 10.23.22.21:9100
  - FEP AP #2 (FEP_AP) 10.23.22.22:9100
  - ATM TX/WEB (ATM) 10.23.22.31:9100
  - ATM DB (ATM) 10.23.22.32:9100
  - CMS DB #1 (CMS_DB) 10.23.22.41:9100
  - CMS DB #2 (CMS_DB) 10.23.22.42:9100
- 모니터링 할 수 있는 프로세스 그룹은 아래와 같다.
  prod
  - Finast_card
  - Finast_card_web
  - db_edb_wait_collector
  - db_postgres_archiver
  - db_postgres_autovacuum_launcher
  - db_postgres_logical_replication
  - db_postgres_master
  - db_postgres_wal_writer
  dev_test
  - CUBEFEP-cm_am
  - CUBEFEP-cm_cb
  - CUBEFEP-cm_cm
  - CUBEFEP-cm_mn
  - CUBEFEP-cm_pm
  - CUBEFEP-cm_sm
  - Finast_card
  - Finast_card_web
  - db_edb_wait_collector
  - db_postgres_archiver
  - db_postgres_autovacuum_launcher
  - db_postgres_logical_replication
  - db_postgres_wal_writer
  dr
  - (현재 등록된 프로세스 그룹 없음)
