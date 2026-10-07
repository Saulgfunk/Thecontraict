import json
from collections.abc import Iterator
from typing import Any

import pytest

from app import chat
from app.config import get_settings
from tests.conftest import Client
from tests.samples import FakeExtractor, msa_docx
from tests.test_api import ALICE, BOB, create_org, create_workspace
from tests.test_contracts import fake, upload  # noqa: F401  (fixture)


class FakeChat:
    """Answers by citing the first content block that mentions the search phrase."""

    model = "fake-chat"

    def __init__(self, phrase: str = "Thereafter it renews", fail: bool = False) -> None:
        self.phrase = phrase
        self.fail = fail
        self.calls: list[list[dict[str, Any]]] = []

    def stream(self, system: str, messages: list[dict[str, Any]]) -> Iterator[Any]:
        self.calls.append(messages)
        yield "The contract "
        if self.fail:
            raise RuntimeError("boom")
        yield "renews for 12 months."
        citations = []
        content = messages[-1]["content"]
        docs = [c for c in content if c["type"] == "document"]
        for i, doc in enumerate(docs):
            for j, block in enumerate(doc["source"]["content"]):
                if self.phrase in block["text"]:
                    citations.append(
                        {
                            "type": "content_block_location",
                            "document_index": i,
                            "start_block_index": j,
                            "end_block_index": j + 1,
                            "cited_text": block["text"],
                        }
                    )
                    break
            if citations:
                break
        yield chat.ChatResult(
            blocks=[
                {"text": "The contract ", "citations": []},
                {"text": "renews for 12 months.", "citations": citations},
            ],
            model=self.model,
            input_tokens=10,
            output_tokens=5,
        )


def events(res) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return [json.loads(line[6:]) for line in res.text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def setup(client_as: Client, fake: FakeExtractor) -> tuple[str, str, str]:  # noqa: F811
    org_id = create_org(client_as)
    ws_id = create_workspace(client_as, org_id, "Client A Ltd")
    contract_id = upload(client_as(ALICE), org_id, ws_id, msa_docx()).json()["id"]
    return org_id, ws_id, contract_id


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeChat:
    m = FakeChat()
    monkeypatch.setattr(chat, "get_chat_model", lambda: m)
    return m


def test_workspace_chat_with_citations(
    client_as: Client, setup: tuple[str, str, str], model: FakeChat
) -> None:
    org_id, ws_id, contract_id = setup
    alice = client_as(ALICE)
    thread = alice.post(f"/organizations/{org_id}/chat/threads", json={"workspace_id": ws_id})
    assert thread.status_code == 201
    thread_id = thread.json()["id"]

    res = alice.post(
        f"/organizations/{org_id}/chat/threads/{thread_id}/messages",
        json={"text": "How long does the renewal last?"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    evs = events(res)
    assert [e["type"] for e in evs] == ["delta", "delta", "message"]
    message = evs[-1]["message"]
    (citation,) = message["blocks"][1]["citations"]
    assert citation["contract_id"] == contract_id
    assert citation["contract_title"] == "Master Services Agreement"
    assert len(citation["clause_refs"]) == 1
    assert "Thereafter it renews automatically" in citation["cited_text"]

    # What the model received: a portfolio overview plus the contract's clauses.
    content = model.calls[0][-1]["content"]
    docs = [c for c in content if c["type"] == "document"]
    assert docs[0]["title"].startswith("Portfolio overview")
    assert "Upcoming calculated deadlines" in docs[0]["source"]["content"][0]["text"]
    assert docs[1]["citations"] == {"enabled": True}
    assert content[-1] == {"type": "text", "text": "How long does the renewal last?"}

    # The thread keeps the history and is titled after the first question.
    detail = alice.get(f"/organizations/{org_id}/chat/threads/{thread_id}").json()
    assert detail["title"] == "How long does the renewal last?"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]

    alice.post(
        f"/organizations/{org_id}/chat/threads/{thread_id}/messages", json={"text": "And notice?"}
    )
    second_call = model.calls[1]
    assert [m["role"] for m in second_call] == ["user", "assistant", "user"]
    assert second_call[1]["content"] == "The contract renews for 12 months."


def test_contract_chat_and_large_workspace_search(
    client_as: Client,
    setup: tuple[str, str, str],
    model: FakeChat,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, ws_id, contract_id = setup
    alice = client_as(ALICE)
    thread_id = alice.post(
        f"/organizations/{org_id}/chat/threads",
        json={"workspace_id": ws_id, "contract_id": contract_id},
    ).json()["id"]
    alice.post(
        f"/organizations/{org_id}/chat/threads/{thread_id}/messages", json={"text": "Renewal?"}
    )
    docs = [c for c in model.calls[0][-1]["content"] if c["type"] == "document"]
    assert [d["title"] for d in docs] == ["Master Services Agreement"]  # no overview

    # Large workspaces send only the clauses that match the question.
    monkeypatch.setattr(chat, "MAX_FULL_TEXT_CHARS", 10)
    ws_thread = alice.post(
        f"/organizations/{org_id}/chat/threads", json={"workspace_id": ws_id}
    ).json()["id"]
    alice.post(
        f"/organizations/{org_id}/chat/threads/{ws_thread}/messages",
        json={"text": "governing law"},
    )
    docs = [c for c in model.calls[1][-1]["content"] if c["type"] == "document"]
    clause_blocks = [b["text"] for b in docs[1]["source"]["content"]]
    assert len(clause_blocks) == 1 and "England and Wales" in clause_blocks[0]


def test_chat_errors_and_privacy(
    client_as: Client, setup: tuple[str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, ws_id, _ = setup
    alice = client_as(ALICE)
    thread_id = alice.post(
        f"/organizations/{org_id}/chat/threads", json={"workspace_id": ws_id}
    ).json()["id"]

    # Not configured: a clear error event, and the question is kept.
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    chat.get_chat_model.cache_clear()
    evs = events(
        alice.post(
            f"/organizations/{org_id}/chat/threads/{thread_id}/messages", json={"text": "Hi"}
        )
    )
    assert evs[-1]["type"] == "error"
    assert "ANTHROPIC_API_KEY" in evs[-1]["detail"]

    # A failure mid-answer keeps the partial text and reports a generic error.
    failing = FakeChat(fail=True)
    monkeypatch.setattr(chat, "get_chat_model", lambda: failing)
    evs = events(
        alice.post(f"/organizations/{org_id}/chat/threads/{thread_id}/messages", json={"text": "Q"})
    )
    assert evs[-1] == {
        "type": "error",
        "detail": "The AI service failed",
        "message": evs[-1]["message"],
    }
    assert evs[-1]["message"]["blocks"][0]["text"] == "The contract "

    # Threads are private, even from org admins and workspace members.
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/members", json={"email": BOB, "role": "viewer"}
    )
    bob = client_as(BOB)
    assert bob.get(f"/organizations/{org_id}/chat/threads/{thread_id}").status_code == 404
    assert bob.get(f"/organizations/{org_id}/chat/threads").json() == []

    assert alice.delete(f"/organizations/{org_id}/chat/threads/{thread_id}").status_code == 204
    assert alice.get(f"/organizations/{org_id}/chat/threads/{thread_id}").status_code == 404


def test_history_params_alternate() -> None:
    from app.models import ChatMessage

    msgs = [
        ChatMessage(role="assistant", blocks=[{"text": "orphan"}]),
        ChatMessage(role="user", blocks=[{"text": "a"}]),
        ChatMessage(role="user", blocks=[{"text": "b"}]),
        ChatMessage(role="assistant", blocks=[{"text": "c"}]),
        ChatMessage(role="assistant", blocks=[], error="failed"),
        ChatMessage(role="user", blocks=[{"text": "unanswered"}]),
    ]
    assert chat.history_params(msgs) == [
        {"role": "user", "content": "a\n\nb"},
        {"role": "assistant", "content": "c"},
    ]
