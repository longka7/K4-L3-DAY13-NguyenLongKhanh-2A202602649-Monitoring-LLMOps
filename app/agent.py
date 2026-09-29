from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, summarize_text
from .prompt_management import resolve_prompt
from .tracing import (
    child_observation,
    get_langfuse_client,
    observe,
    propagate_attributes,
    tracing_enabled,
)

# Giá giả lập (USD / 1M token) — dùng chung cho cost trong log, metrics và trace.
PRICE_INPUT_PER_M = 3
PRICE_OUTPUT_PER_M = 15


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    # Để log nối được sang trace (tìm trace theo trace_id thay vì dò theo correlation_id)
    trace_id: str | None = None
    prompt_version: str | None = None
    prompt_label: str | None = None


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_client = get_langfuse_client()
        with propagate_attributes(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
            trace_name="day13-agent-request",
            environment=os.getenv("APP_ENV", "dev"),
            metadata={
                "feature": feature,
                "model": self.model,
                "correlation_id": correlation_id,
            },
        ):
            started = time.perf_counter()
            get_trace_id = getattr(langfuse_client, "get_current_trace_id", None)
            trace_id = get_trace_id() if callable(get_trace_id) else None
            # Child 1 — retrieval. Chỉ ghi preview đã scrub, không ghi raw query/doc.
            with child_observation(
                langfuse_client,
                name="rag-retrieval",
                as_type="retriever",
                input={"query_preview": summarize_text(message)},
                metadata={"correlation_id": correlation_id, "feature": feature},
            ) as retrieval_obs:
                try:
                    docs = retrieve(message)
                except Exception as exc:
                    retrieval_obs.update(
                        level="ERROR",
                        status_message=type(exc).__name__,
                        metadata={"retrieval_success": False},
                    )
                    raise
                retrieval_obs.update(
                    output={"doc_count": len(docs)},
                    metadata={"retrieval_success": True},
                )
            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=tracing_enabled(),
            )
            langfuse_client.update_current_span(
                metadata={
                    "doc_count": len(docs),
                    "query_preview": summarize_text(message),
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error or "",
                },
                version=prompt.version,
            )
            # Child 2 — generation: gắn model, prompt managed (link tới prompt version),
            # usage và cost. Không truyền raw prompt/output (có thể chứa PII).
            with propagate_attributes(prompt=prompt.managed_prompt), child_observation(
                langfuse_client,
                name="llm-generation",
                as_type="generation",
                model=self.model,
                prompt=prompt.managed_prompt,
                input={"prompt_name": prompt.name, "prompt_version": prompt.version},
                metadata={
                    "correlation_id": correlation_id,
                    "prompt_label": prompt.label,
                    "prompt_source": prompt.source,
                },
            ) as generation_obs:
                llm_started_at = datetime.now(timezone.utc)
                response = self.llm.generate(prompt.text)
                cost_in, cost_out = self._cost_parts(
                    response.usage.input_tokens, response.usage.output_tokens
                )
                generation_obs.update(
                    output={"answer_preview": summarize_text(response.text)},
                    completion_start_time=llm_started_at + timedelta(milliseconds=response.ttft_ms),
                    usage_details={
                        "input": response.usage.input_tokens,
                        "output": response.usage.output_tokens,
                    },
                    cost_details={"input": cost_in, "output": cost_out, "total": cost_in + cost_out},
                    metadata={"ttft_ms": response.ttft_ms},
                )
            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
            trace_id=trace_id,
            prompt_version=prompt.version,
            prompt_label=prompt.label,
        )

    def _cost_parts(self, tokens_in: int, tokens_out: int) -> tuple[float, float]:
        return (tokens_in / 1_000_000) * PRICE_INPUT_PER_M, (tokens_out / 1_000_000) * PRICE_OUTPUT_PER_M

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost, output_cost = self._cost_parts(tokens_in, tokens_out)
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
