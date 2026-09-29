# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Long Khánh
- **MSSV:** 2A202602649
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/longka7/K4-L3-DAY13-NguyenLongKhanh-2A202602649-Monitoring-LLMOps
- **Commit SHA cuối:** SHA nộp trên LMS là commit mới nhất của nhánh `main` (commit chứa file này). Code + evidence chính nằm ở các commit `220240d` (CP1), `b92d81f` (CP2), `68d5bbc` (CP3).
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, affected feature `monitoring`)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602649`

## 2. Evidence index

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) · cây observation qua API: [`evidence/07-trace-tree-api.txt`](evidence/07-trace-tree-api.txt) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt rollback | [`evidence/10-prompt-rollback.png`](evidence/10-prompt-rollback.png) · trạng thái label trước/sau: [`evidence/10-prompt-rollback.txt`](evidence/10-prompt-rollback.txt) · trace IDs: [`evidence/10-prompt-traces.txt`](evidence/10-prompt-traces.txt) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) · so sánh span qua API: [`evidence/14-incident-trace.txt`](evidence/14-incident-trace.txt) |
| Kiểm chứng fix incident | [`evidence/15-incident-fix-verification.txt`](evidence/15-incident-fix-verification.txt) |
| Baseline (trước khi sửa) | [`evidence/baseline/`](evidence/baseline/) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu `correlation_id`, thiếu enrichment) | 100/100 | 4/4 hạng mục đạt |
| `validate_dashboard.py` | 6/6 (chỉ contract) | 6/6 + dashboard runtime có dữ liệu | contract không đổi; dashboard dựng bằng `scripts/build_dashboard.py` |
| `pytest` | 22 passed | 34 passed | +12 test: PII (CCCD, thẻ, hộ chiếu, không che nhầm ID hex), correlation ID, không rò context, scrub mọi field |
| Số traces hợp lệ | 0 (chưa có key, `tracing_enabled=false`) | 104 trace `lab-agent-run` trong project cá nhân | mỗi trace có child `prompt-fetch`, `rag-retrieval`, `llm-generation` |
| Số PII leak | 0 trong log (validator) nhưng scrubber chỉ chạy trên `payload`/`event` | 0 (grep 4 loại PII giả trong toàn bộ `data/logs.jsonl` = 0) | scrub mọi field chuỗi, trước khi ghi file |
| Latency P95 / TTFT P95 | 159 ms / 55 ms (10 req, chưa tracing) | 162 ms / 55 ms (10 req bình thường sau mọi fix) | tracing Langfuse gần như không thêm latency |
| Retrieval success rate | 100% (starter ghi cứng `tool_success=True`) | 100% bình thường; 88,76% trong cửa sổ có practice `tool_fail` | lỗi retrieval ghi `request_failed` + `tool_success=false` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `app/middleware.py` gọi `clear_contextvars()` đầu mỗi request, rồi `resolve_correlation_id()`: giữ `x-request-id` của upstream nếu hợp lệ (1–64 ký tự `[A-Za-z0-9._:-]`, không chứa PII), ngược lại sinh `req-<8-hex>`. ID được bind vào structlog contextvars, truyền vào `agent.run` (metadata trace) và trả lại qua header `x-request-id` cùng `x-response-time-ms`. Header độc hại (`x"\n{"event":"fake"}`) hay header là email/SĐT đều bị thay bằng ID mới (test `test_tu_choi_id_nguy_hiem_hoac_chua_pii`).
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256 12 ký tự, không log `user_id` gốc), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`, `trace_id`, `prompt_version`, `prompt_label`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` được đăng ký trong `configure_logging()` ngay sau `TimeStamper` và **trước** `JsonlFileProcessor`/`JSONRenderer`, nên dữ liệu thô không bao giờ được serialize xuống đĩa hay stdout. Khác starter (chỉ scrub `payload` và `event`), processor scrub **mọi field chuỗi, kể cả lồng trong dict/list**, vì PII có thể lọt qua error detail hay field thêm sau này. Pattern trong `app/pii.py`: thẻ (chạy trước để không bị cắt thành CCCD), email, CCCD 12 số, SĐT VN (`0…`/`+84…`, có dấu cách/chấm/gạch), hộ chiếu VN.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 100/100; gửi 2 request chứa PII giả (email, SĐT, CCCD, thẻ) và log chỉ còn `[REDACTED_*]`, `grep` 4 chuỗi thô trong toàn bộ file log = 0 ([05-pii-redaction.txt](evidence/05-pii-redaction.txt)); unit test cho từng loại.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** key trong `.env` là của project `day13-k4-l3a-2A202602649` (`auth_check()` = True); mọi request đều do tôi chạy (`load_test.py`, challenge, curl có `x-request-id` tự đặt như `req-0000b001`). `trace_id` được ghi ngay trong log `response_sent`, nên mỗi trace ID trong báo cáo đối chiếu được với một dòng log của repo này.
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (type `agent`, decorator `@observe`) → con `prompt-fetch` (span), `rag-retrieval` (type `retriever`, input là preview đã scrub, output `doc_count`, level `ERROR` khi retrieval lỗi) và `llm-generation` (type `generation`: `model=claude-sonnet-4-5`, `prompt` = prompt managed nên Langfuse link sang đúng version, `usage_details` input/output, `cost_details` input/output/total, `completion_start_time` = start + TTFT). Không truyền raw prompt/answer (có thể chứa PII), chỉ preview đã scrub. Helper `child_observation()` trong `app/tracing.py` dùng `start_as_current_observation` của SDK v4 và tự thành no-op khi tracing tắt/client giả trong test. Xác nhận qua API: [07-trace-tree-api.txt](evidence/07-trace-tree-api.txt).
- **Cách nối trace với log:** hai chiều — trace metadata (root + từng child) có `correlation_id`; log `response_sent` có `trace_id`.
- **Prompt name:** `day13-chat` (text prompt, giữ 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`).
- **Version/label baseline:** v1, labels `baseline` (+ `production` lúc đầu) — template gốc.
- **Version/label candidate:** v2, label `candidate` — thêm dòng `Answer in at most 3 short bullet points, only from Docs.`
- **Trace ID của mỗi version** (cùng input *"Explain why metrics traces and logs work together"*, xem [10-prompt-traces.txt](evidence/10-prompt-traces.txt)):

  | Request | Label | Version | Trace ID |
  |---|---|---|---|
  | `req-0000b001` | baseline | 1 | `c995ec46bb992b5875154ccf172f1fe3` |
  | `req-0000c002` | candidate | 2 | `57e1dac8a61baf38ccc5d6a3647d8941` |
  | `req-0000a005` | production (sau promote) | 2 | `53f067842ee69a2c26c0365224dfa7c8` |
  | `req-0000a006` | production (sau rollback) | 1 | `ca759857e9615811255fbe0a7b2dfc68` |

- **Cách promote và rollback `production`:** `python scripts/prompt_versions.py promote 2` (gán label `production` cho v2, Langfuse tự gỡ khỏi v1) rồi `promote 1` để rollback; restart API để bỏ cache prompt 60 s. Trạng thái label trước/sau lưu ở [10-prompt-rollback.txt](evidence/10-prompt-rollback.txt). App không cần deploy lại code để đổi prompt — chỉ đổi label.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `python scripts/build_dashboard.py` đọc `config/dashboard.yaml` (contract giữ nguyên) + `data/logs.jsonl`, sinh `data/dashboard.html` (Chart.js): latency P50/P95/P99 + TTFT P95; traffic req/phút; error rate + retrieval success + breakdown `error_type`; cost theo phút + lũy kế; tokens in/out; mean quality. Mỗi panel có đơn vị, threshold line đúng contract, time range 60 phút, auto-refresh 30 s. Tùy chọn `--feature` để khoanh vùng incident. Ảnh: [11-dashboard-overview.png](evidence/11-dashboard-overview.png) (có practice `rag_slow`, `tool_fail`, `cost_spike` và challenge).
- **SLO và lý do chọn:** `fast_successful_requests`, cửa sổ 28 ngày, target 99,5%; good = `response_sent` với `latency_ms <= 2000`. Tôi **hạ ngưỡng từ 3000 ms xuống 2000 ms** vì baseline bình thường có P99 = 1090 ms, còn practice `rag_slow` cho latency 2,6–2,7 s — **dưới** 3000 ms, tức SLO cũ không hề phát hiện sự cố RAG chậm. 2000 ms ≈ 2 × P99 vẫn đủ headroom. Ngưỡng p95 ≤ 3000 ms của dashboard giữ nguyên như contract (trần cứng).
- **Cách tính error budget:** budget = `total_requests_28d × 0,5%`. Ví dụ 1.000 req/ngày → 28.000 req → tối đa 140 request xấu. Practice `tool_fail` làm hỏng 10 request trong khoảng 1 phút = 7,1% budget tháng; `rag_slow` thêm 7,1% — hai sự cố ngắn đã đốt ~14% budget, nên alert phải có duration ngắn. Chi tiết: `config/slo.yaml`.
- **Ba alert và runbook tương ứng** (`config/alert_rules.yaml`, [`docs/alerts.md`](../docs/alerts.md)), đều symptom-based, có duration, severity, owner, Slack channel:
  1. `ChatLatencyP95High` — warning, P95 > 2000 ms trong 5m → `#day13-llmops-alerts`.
  2. `ChatErrorRateHigh` — critical, error rate > 2% trong 5m → `#day13-llmops-oncall`.
  3. `CostPerRequestSpike` — warning, cost trung bình/request > 0,005 USD (≈ 2× baseline 0,0021) trong 10m → `#day13-llmops-alerts`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (file do Lab Coach gửi, lưu tại `config/challenge.json`, không sửa, không commit).
- **Khoảng thời gian điều tra:** 2026-09-29 09:15:41 → 09:15:55 UTC (`inject_incident.py` + `load_test.py --challenge --concurrency 5`).
- **Triệu chứng từ metrics:** dashboard lọc `feature=monitoring` ([12-incident-metric.png](evidence/12-incident-metric.png)): **P50 = 2667 ms, P95 = 2678 ms** (mọi request chậm, vượt SLO 2000 ms), trong khi **TTFT P95 = 55 ms** (bằng baseline) và error rate 0%. Kết luận từ metrics: chậm nằm **trước** bước LLM trả token đầu, không phải lỗi. Phía client còn tệ hơn: cả 5 request đều mất ~13,4 s.
- **Log line và correlation ID liên quan** ([13-incident-log.txt](evidence/13-incident-log.txt)): `jq 'select(.event=="response_sent" and .feature=="monitoring" and .latency_ms>2000)'` ra 5 dòng; chọn `req-309c0d9d`: `latency_ms=2664, ttft_ms=50, tool_success=true, trace_id=a8628692e939913889d253bb71e9e293`. Log cũng cho thấy `request_received` của request sau chỉ xuất hiện khi request trước đã `response_sent` (cách nhau đều ~2,67 s) → server xử lý **nối tiếp** 5 request đồng thời.
- **Trace ID và span gây ảnh hưởng:** trace `a8628692e939913889d253bb71e9e293` (cùng `correlation_id=req-309c0d9d`): root 2665 ms, **`rag-retrieval` = 2506 ms (94%)**, `llm-generation` = 155 ms (TTFT 0,05 s). So với trace bình thường `91855decb0b513ea343eb7199ec67b53`: retrieval 0 ms, generation 156 ms ([14-incident-trace.txt](evidence/14-incident-trace.txt)).
- **Root cause:** bước retrieval (vector store) chậm thêm ~2,5 s/request (incident `rag_slow`). Bị khuếch đại bởi lỗi thiết kế: `agent.run()` là code đồng bộ (blocking) nhưng được gọi thẳng trong endpoint `async def`, nên một retrieval chậm **chặn event loop** — 5 request đồng thời bị xếp hàng, request cuối chờ 5 × 2,67 ≈ 13,4 s. `latency_ms` bắt đầu đo bên trong `agent.run` nên **không thấy** thời gian xếp hàng này.
- **Fix action:**
  1. Mitigation: tắt nguồn chậm (`inject_incident.py --disable`) → request `monitoring` về 0,16–0,17 s.
  2. Code fix (`app/main.py`): chạy `agent.run` qua `run_in_threadpool`. Chạy lại challenge với `rag_slow` **vẫn bật**: 5 request được nhận cùng lúc (09:17:46.737) và trả về cùng lúc, client ~3,46 s thay vì 13,4 s ([15-incident-fix-verification.txt](evidence/15-incident-fix-verification.txt)); context/correlation ID không lẫn giữa các thread.
- **Preventive measure:**
  1. Alert `ChatLatencyP95High` (P95 > 2 s / 5 phút) với SLO ngưỡng 2000 ms — ngưỡng 3000 ms cũ không bắt được sự cố này.
  2. Timeout + fallback cho retrieval (vd 800 ms, quá hạn thì trả lời "chưa có tài liệu") để một dependency chậm không kéo cả request.
  3. Load test luôn chạy với `--concurrency > 1` — chạy tuần tự sẽ không bao giờ lộ lỗi chặn event loop.
  4. Đo cả thời gian xếp hàng/phía client (header `x-response-time-ms`, metric ở gateway), không chỉ `latency_ms` bên trong agent.
  5. Thêm span `prompt-fetch`: khi rerun tôi thấy khoảng trống 745 ms không thuộc span nào giữa retrieval và generation (fetch prompt Langfuse lúc cache lạnh) — nay đã hiện trong trace.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** scrub PII ở **mọi field chuỗi** trong `scrub_event` thay vì chỉ `payload`/`event` như starter. Lý do: validator chỉ kiểm tra dữ liệu mẫu hiện có; trong vận hành thật PII lọt qua chỗ không ngờ — error detail, header client gửi lên, field mới thêm. Scrub toàn bộ an toàn theo mặc định. Đánh đổi: phải loại trừ các ID hệ thống (xem blocker dưới).
- **Một lỗi/blocker đã gặp:** khi rerun challenge, một log có `trace_id = "8968fc9b[REDACTED_CCCD]c176ae223299"` — chính scrubber của tôi đã che nhầm 12 chữ số liên tiếp nằm giữa ID hex thành "CCCD", làm log đó **không nối được sang trace**.
- **Cách tìm nguyên nhân và xử lý:** thấy `[REDACTED_CCCD]` trong cột `trace_id` khi in timeline → pattern `(?<!\d)\d{12}(?!\d)` chỉ chặn chữ số ở hai biên, không chặn chữ cái hex. Sửa 2 lớp: (1) biên của pattern số đổi thành `(?<![0-9A-Za-z])…(?![0-9A-Za-z])`; (2) bỏ qua field ID hệ thống (`trace_id`, `correlation_id` — đã được middleware lọc PII —, `user_id_hash`). Thêm 2 test hồi quy với chính ID hex đó; rerun: 0 ID bị che. Blocker khác: API `GET /api/public/traces/{id}` trả **410** cho organization tạo sau 16/09/2026 → chuyển sang `GET /api/public/v2/observations?traceId=…` (`scripts/langfuse_trace_tree.py`); và `update_prompt` trả 400 nếu gửi kèm label `latest` (do Langfuse tự quản) → lọc bỏ `latest`.
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời *có vấn đề gì và từ lúc nào* (P50/P95 tăng nhưng TTFT không tăng, lỗi = 0 → chậm trước LLM); logs trả lời *request nào bị ảnh hưởng* (lọc theo khoảng thời gian/feature/latency, lấy `correlation_id` + `trace_id`, và thấy timeline nối tiếp); trace trả lời *bước nào gây ra* (so duration từng span với trace bình thường → `rag-retrieval` 2506 ms). Mỗi tầng thu hẹp phạm vi cho tầng sau; `correlation_id`/`trace_id` là khóa nối.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt là "code" thay đổi hành vi mà không qua deploy — gắn version vào generation giúp trả lời "request này chạy prompt nào", và label `production` cho phép rollback trong vài giây (đã làm v2 → v1). Token/cost trên từng generation cho biết thay đổi prompt/model làm đắt lên bao nhiêu (practice `cost_spike`: tokens_out ×4). SLO + error budget biến "chậm/lỗi" thành con số quyết định được: khi budget cạn thì đóng băng thay đổi prompt, chỉ cho rollback.
- **Điều quan trọng nhất đã học:** số liệu phía server có thể nói dối — `latency_ms` 2,67 s trong khi người dùng chờ 13,4 s — vì điểm bắt đầu đo nằm sau hàng đợi. Phải so tín hiệu từ nhiều phía (client, timeline log, trace) mới ra nguyên nhân thật.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** dashboard là HTML sinh từ log (chạy lại script để cập nhật), chưa phải hệ thống live như Grafana; alert mới ở mức định nghĩa + runbook, chưa nối Slack webhook thật; chưa có timeout/fallback cho retrieval trong code (mới đề xuất); `quality_score` vẫn là heuristic của starter.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối (còn thiếu ảnh UI Langfuse 06–10, 14).
- [x] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret (chờ chụp ảnh UI).
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
