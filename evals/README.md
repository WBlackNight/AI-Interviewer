# 评估与预览脚本导航

常用入口为[tools/project.py](../tools/README.md)。本目录保留现有文件位置，避免破坏CI和历史命令。

前端检查：`python tools/project.py check`。后端测试：`python -m pytest backend/tests -q`。冒烟脚本自建隔离库，不应替代生产数据验收。供应商探针可能联网并计费，应先读脚本参数与对应接入文档；统一check不会自动运行这些探针。

## 前端与网关离线检查

- [account_menu_check.mjs](account_menu_check.mjs)
- [account_ui_check.mjs](account_ui_check.mjs)
- [carousel_check.mjs](carousel_check.mjs)
- [home_interaction_check.mjs](home_interaction_check.mjs)
- [microphone_check.mjs](microphone_check.mjs)
- [native_home_check.py](native_home_check.py)
- [native_interview_test.cjs](native_interview_test.cjs)
- [realtime_ui_check.mjs](realtime_ui_check.mjs)
- [test_native_home_gateway.py](test_native_home_gateway.py)
- [ui_core_check.mjs](ui_core_check.mjs)
- [voice_ui_check.mjs](voice_ui_check.mjs)

## 本机预览与测试邮件

- [local_test_mail.py](local_test_mail.py)
- [native_home_gateway.py](native_home_gateway.py)
- [native_home_preview.py](native_home_preview.py)
- [preparation_preview.py](preparation_preview.py)
- [review_ui_preview.py](review_ui_preview.py)

## 业务冒烟与隔离数据

- [account_smoke.py](account_smoke.py)
- [cancellation_smoke.py](cancellation_smoke.py)
- [catalog_smoke.py](catalog_smoke.py)
- [coverage_smoke.py](coverage_smoke.py)
- [dashboard_smoke.py](dashboard_smoke.py)
- [history_filters_smoke.py](history_filters_smoke.py)
- [practice_smoke.py](practice_smoke.py)
- [preparation_smoke.py](preparation_smoke.py)
- [question_marks_smoke.py](question_marks_smoke.py)
- [revision_notes_smoke.py](revision_notes_smoke.py)
- [revision_practice_smoke.py](revision_practice_smoke.py)
- [revision_schedule_smoke.py](revision_schedule_smoke.py)
- [revision_smoke.py](revision_smoke.py)
- [smoke_e2e.py](smoke_e2e.py)

## 供应商探针与用量核对

- [doubao_realtime_probe.py](doubao_realtime_probe.py)
- [doubao_voice_probe.py](doubao_voice_probe.py)
- [embedding_ping.py](embedding_ping.py)
- [latency_probe.py](latency_probe.py)
- [llm_ping.py](llm_ping.py)
- [reconcile_llm_usage.py](reconcile_llm_usage.py)
- [sandbox_probe.py](sandbox_probe.py)

## 题库、检索与审校

- [audit_question_bank.py](audit_question_bank.py)
- [build_question_index.py](build_question_index.py)
- [prepare_question_release.py](prepare_question_release.py)
- [retrieval_eval.py](retrieval_eval.py)
- [review_candidate_answers.py](review_candidate_answers.py)
