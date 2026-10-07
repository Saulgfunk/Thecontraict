"""Exercise the real Anthropic SDK code paths against a simulated API.

These tests catch mistakes in how we call the SDK (parameter names, beta headers,
structured-output schemas, document and citation shapes, stream parsing) without
network access or an API key. The simulated responses follow the Messages API
streaming format.
"""

import json
import uuid
from datetime import date
from typing import Any

import httpx2
import pytest

from app.chat import ChatResult, ClaudeChat, SourceDoc, resolve_citations
from app.pipeline.extract import ClaudeExtractor, ContractExtraction, render_clauses


def sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def text_stream(
    chunks: list[str], citations: list[dict[str, Any]] | None = None, stop_reason: str = "end_turn"
) -> bytes:
    events: list[dict[str, Any]] = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1234, "output_tokens": 1},
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ]
    for c in chunks:
        events.append(
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": c}}
        )
    for citation in citations or []:
        events.append(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "citations_delta", "citation": citation},
            }
        )
    events += [
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 321},
        },
        {"type": "message_stop"},
    ]
    return sse(events)


class FakeAPI:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requests: list[httpx2.Request] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(
            200, content=self.body, headers={"content-type": "text/event-stream"}
        )

    @property
    def last_json(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)

    def client(self):  # type: ignore[no-untyped-def]
        import anthropic

        return anthropic.Anthropic(
            api_key="test-key",
            http_client=httpx2.Client(transport=httpx2.MockTransport(self.handler)),
            max_retries=0,
        )


CONTRACT_ID = uuid.uuid4()

EXTRACTION = {
    "title": "Master Services Agreement",
    "contract_type": "Services",
    "summary": "Acme supplies services.",
    "parties": [{"name": "Acme Ltd", "role": "Supplier"}],
    "counterparty_name": "Acme Ltd",
    "effective_date": {
        "value": "2025-01-01",
        "source": {
            "clause_refs": ["C2"],
            "quote": "commences on 1 January 2025",
            "confidence": 0.9,
        },
    },
    "end_date": None,
    "initial_term": {
        "value": {"amount": 24, "unit": "months"},
        "source": {"clause_refs": ["C2"], "quote": "24 months", "confidence": 0.9},
    },
    "auto_renews": None,
    "renewal_term": None,
    "governing_law": None,
    "currency": "EUR",
    "contract_value": None,
    "notice_details": None,
    "date_rules": [],
    "payment_terms": [],
}


def _objects(schema: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            found.append(schema)
        for value in schema.values():
            found += _objects(value)
    elif isinstance(schema, list):
        for value in schema:
            found += _objects(value)
    return found


def test_extraction_request_and_parsing() -> None:
    api = FakeAPI(text_stream([json.dumps(EXTRACTION)[:50], json.dumps(EXTRACTION)[50:]]))
    extractor = ClaudeExtractor("test-key", "claude-opus-5-5", "high")
    extractor.client = api.client()

    xml = render_clauses([("C1", "1", "TERM", 1, "Commences on 1 January 2025.")])
    out = extractor.extract(xml, "Context: org")

    assert isinstance(out.extraction, ContractExtraction)
    assert out.extraction.effective_date and out.extraction.effective_date.value == date(2025, 1, 1)
    assert (out.input_tokens, out.output_tokens) == (1234, 321)

    request = api.requests[-1]
    assert request.url.path == "/v1/messages"
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    body = api.last_json
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["stream"] is True
    assert body["output_config"]["effort"] == "high"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    # Structured outputs require additionalProperties: false on every object.
    objects = _objects(fmt["schema"])
    assert objects and all(o.get("additionalProperties") is False for o in objects)
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    content = body["messages"][0]["content"]
    assert content[0]["text"].startswith("<contract>")
    assert content[1]["text"] == "Context: org"
    assert "thinking" not in body  # adaptive by default; explicit configs can be rejected
    assert "temperature" not in body


def test_extraction_stop_reasons() -> None:
    from app.pipeline.extract import ExtractionError

    for reason, message in (("refusal", "declined"), ("max_tokens", "too long")):
        api = FakeAPI(text_stream(['{"title": '], stop_reason=reason))
        extractor = ClaudeExtractor("test-key", "claude-opus-5-5", "high")
        extractor.client = api.client()
        with pytest.raises(ExtractionError, match=message):
            extractor.extract("<contract></contract>", "ctx")


def test_ocr_request_sends_pdf_document() -> None:
    pages = {"pages": [{"page_number": 1, "text": "1. TERM\nCommences..."}]}
    api = FakeAPI(text_stream([json.dumps(pages)]))
    extractor = ClaudeExtractor("test-key", "claude-opus-5-5", "high")
    extractor.client = api.client()
    result = extractor.transcribe_pdf(b"%PDF-1.4 fake")
    assert result[0].page_number == 1
    doc = api.last_json["messages"][0]["content"][0]
    assert doc["type"] == "document"
    assert doc["source"]["type"] == "base64"
    assert doc["source"]["media_type"] == "application/pdf"


def test_chat_request_streaming_and_citations() -> None:
    citation = {
        "type": "content_block_location",
        "cited_text": "[C5] 2.2 Thereafter it renews automatically",
        "document_index": 1,
        "document_title": "MSA",
        "start_block_index": 0,
        "end_block_index": 1,
    }
    api = FakeAPI(text_stream(["It renews ", "yearly."], [citation]))
    model = ClaudeChat("test-key", "claude-opus-5-5", "medium")
    model.client = api.client()

    sources = [
        SourceDoc(None, "Portfolio overview", None, ["MSA: facts"], [None]),
        SourceDoc(
            CONTRACT_ID,
            "MSA",
            "Counterparty: Acme",
            ["[C5] 2.2 Thereafter it renews"],
            ["C5"],
            [CONTRACT_ID],
        ),
    ]
    messages = [
        {
            "role": "user",
            "content": [s.to_param() for s in sources]
            + [{"type": "text", "text": "Does it renew?"}],
        }
    ]
    items = list(model.stream("system prompt", messages))

    assert items[:-1] == ["It renews ", "yearly."]
    result = items[-1]
    assert isinstance(result, ChatResult)
    assert result.blocks[0]["text"] == "It renews yearly."
    assert result.blocks[0]["citations"][0]["start_block_index"] == 0
    (resolved,) = resolve_citations(result.blocks[0]["citations"], sources, {CONTRACT_ID: "MSA"})
    assert resolved["contract_id"] == str(CONTRACT_ID)
    assert resolved["clause_refs"] == ["C5"]

    body = api.last_json
    assert body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "medium"}
    doc = body["messages"][0]["content"][1]
    assert doc["type"] == "document"
    assert doc["source"]["type"] == "content"
    assert doc["source"]["content"] == [{"type": "text", "text": "[C5] 2.2 Thereafter it renews"}]
    assert doc["citations"] == {"enabled": True}
    assert doc["context"] == "Counterparty: Acme"
