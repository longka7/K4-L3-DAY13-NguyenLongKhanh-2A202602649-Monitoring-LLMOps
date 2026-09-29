# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.
Nguồn chung: `data/logs.jsonl` (cùng nguồn dashboard `scripts/build_dashboard.py`); trace mở trong Langfuse project `day13-k4-l3a-2A202602649`.
Quy trình chung: **Metric** (panel nào xấu, từ lúc nào) → **Log** (lọc event trong khoảng đó, lấy `correlation_id`/`trace_id`) → **Trace** (span nào chậm/lỗi).

## Alert 1

- Tên: `ChatLatencyP95High`
- Severity: warning
- Duration: 5m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: `primary_slo.fast_successful_requests` (good = `response_sent` và `latency_ms <= 2000`, target 99.5% / 28d)
- Điều kiện và thời gian duy trì: P95 `latency_ms` của `response_sent` > 2000 ms liên tục 5 phút.
- Ảnh hưởng tới người dùng: câu trả lời chậm rõ rệt (baseline P95 ≈ 1.0 s); mỗi request > 2 s đốt error budget.
- Ba bước kiểm tra đầu tiên:
  1. Panel **Latency**: chỉ P95/P99 tăng hay cả P50? TTFT P95 có tăng không (TTFT tăng ⇒ chậm ở LLM, TTFT bình thường ⇒ chậm trước LLM)?
  2. Lọc log chậm: `jq -c 'select(.event=="response_sent" and .latency_ms>2000) | {ts,correlation_id,trace_id,feature,ttft_ms}' data/logs.jsonl`
  3. Mở trace theo `trace_id`: so duration `rag-retrieval` với `llm-generation` để khoanh vùng span chậm.
- Mitigation tạm thời: nếu `rag-retrieval` chậm → giảm top-k/timeout retrieval, trả lời fallback "chưa có tài liệu" thay vì treo; nếu `llm-generation` chậm → chuyển sang model nhanh hơn hoặc giảm `max_tokens`; rollback prompt label `production` nếu vừa promote version mới.
- Owner: Nguyen Long Khanh (on-call LLMOps)

## Alert 2

- Tên: `ChatErrorRateHigh`
- Severity: critical
- Duration: 5m
- Kênh thông báo: Slack `#day13-llmops-oncall`
- SLI/SLO liên quan: `primary_slo.fast_successful_requests`; guardrail `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `request_failed / request_received * 100 > 2%` liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500, không có câu trả lời; mỗi lỗi là 1 request xấu (practice `tool_fail`: 10 lỗi ≈ 7% error budget tháng trong 1 phút).
- Ba bước kiểm tra đầu tiên:
  1. Panel **Errors**: error rate và retrieval success có giảm cùng lúc không; breakdown `error_type` là gì.
  2. Lọc log lỗi: `jq -c 'select(.event=="request_failed") | {ts,correlation_id,error_type,tool_name,tool_success}' data/logs.jsonl`
  3. Mở trace có cùng `correlation_id` (lọc metadata trong Langfuse): span nào có `level=ERROR` / `status_message`.
- Mitigation tạm thời: lỗi ở `rag-retrieval` → bật fallback trả lời không dùng tài liệu (kèm cảnh báo), retry có backoff, chuyển sang vector store dự phòng; lỗi ở `llm-generation` → failover provider/model; nếu lỗi bắt đầu sau khi đổi prompt/model → rollback ngay.
- Owner: Nguyen Long Khanh (on-call LLMOps)

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: warning
- Duration: 10m
- Kênh thông báo: Slack `#day13-llmops-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`; panel **Cost** và **Tokens**
- Điều kiện và thời gian duy trì: trung bình `cost_usd` mỗi `response_sent` > 0.005 USD (≈ 2× baseline 0.0021) liên tục 10 phút.
- Ảnh hưởng tới người dùng: không thấy ngay, nhưng đốt ngân sách nhanh ⇒ nguy cơ chạm trần ngày và bị chặn dịch vụ; câu trả lời dài bất thường cũng giảm trải nghiệm.
- Ba bước kiểm tra đầu tiên:
  1. Panel **Tokens**: tăng ở `tokens_in` (prompt/context phình) hay `tokens_out` (trả lời dài)?
  2. Lọc log đắt: `jq -c 'select(.event=="response_sent" and .cost_usd>0.005) | {ts,correlation_id,trace_id,prompt_version,tokens_in,tokens_out}' data/logs.jsonl`
  3. Mở trace: generation `usage`/`cost` và prompt version đang gắn — có trùng thời điểm đổi prompt label không.
- Mitigation tạm thời: đặt `max_tokens` cho output, rollback prompt label `production` về version trước, bật cache câu trả lời lặp lại, giới hạn độ dài context retrieval.
- Owner: Nguyen Long Khanh (on-call LLMOps)
