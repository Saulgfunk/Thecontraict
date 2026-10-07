import io
from typing import Any

import pytest
from openpyxl import load_workbook

from app import chat, drafting
from tests.conftest import Client
from tests.samples import FakeExtractor, msa_docx
from tests.test_api import ALICE, BOB, create_org, create_workspace
from tests.test_chat import FakeChat, events
from tests.test_contracts import fake, upload  # noqa: F401  (fixture)


@pytest.fixture
def setup(client_as: Client, fake: FakeExtractor) -> tuple[str, str, str]:  # noqa: F811
    org_id = create_org(client_as)
    client_as(ALICE).patch(f"/organizations/{org_id}", json={"default_country": "GB"})
    ws_id = create_workspace(client_as, org_id, "Client A Ltd")
    contract_id = upload(client_as(ALICE), org_id, ws_id, msa_docx()).json()["id"]
    return org_id, ws_id, contract_id


def notice_deadline(client, org_id: str, contract_id: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    detail = client.get(f"/organizations/{org_id}/contracts/{contract_id}").json()
    return next(d for d in detail["deadlines"] if d["kind"] == "notice")


def test_decisions_are_recorded_and_survive_recalculation(
    client_as: Client, setup: tuple[str, str, str]
) -> None:
    org_id, ws_id, contract_id = setup
    alice = client_as(ALICE)
    deadline = notice_deadline(alice, org_id, contract_id)

    res = alice.patch(
        f"/organizations/{org_id}/deadlines/{deadline['id']}",
        json={"decision": "terminate", "decision_note": "Moving to another supplier."},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "terminate"
    assert body["status"] == "done"  # a decision closes the deadline
    assert body["decided_by_id"] and body["decided_at"]

    # Recalculating the contract keeps the decision.
    alice.patch(f"/organizations/{org_id}/contracts/{contract_id}", json={"title": "MSA"})
    again = notice_deadline(alice, org_id, contract_id)
    assert again["id"] != deadline["id"]
    assert (again["decision"], again["decision_note"]) == (
        "terminate",
        "Moving to another supplier.",
    )

    # Clearing the decision; status can be reopened explicitly.
    res = alice.patch(
        f"/organizations/{org_id}/deadlines/{again['id']}",
        json={"decision": None, "status": "open"},
    )
    assert (res.json()["decision"], res.json()["status"], res.json()["decided_at"]) == (
        None,
        "open",
        None,
    )

    events_ = alice.get(f"/organizations/{org_id}/audit-events").json()
    assert "deadline.decision_recorded" in [e["action"] for e in events_]

    # Viewers can't decide.
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/members", json={"email": BOB, "role": "viewer"}
    )
    res = client_as(BOB).patch(
        f"/organizations/{org_id}/deadlines/{again['id']}", json={"decision": "renew"}
    )
    assert res.status_code == 403


def test_draft_notice(
    client_as: Client, setup: tuple[str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _, contract_id = setup
    alice = client_as(ALICE)
    model = FakeChat()
    seen: dict[str, Any] = {}
    original = model.stream

    def stream(system: str, messages: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
        seen["system"] = system
        return original(system, messages)

    model.stream = stream  # type: ignore[method-assign]
    monkeypatch.setattr(chat, "get_chat_model", lambda: model)

    deadline = notice_deadline(alice, org_id, contract_id)
    res = alice.post(
        f"/organizations/{org_id}/contracts/{contract_id}/draft-notice",
        json={
            "kind": "non_renewal",
            "deadline_id": deadline["id"],
            "sender": "Client A Ltd, by its General Counsel",
            "instructions": "Keep it short.",
        },
    )
    assert res.status_code == 200
    evs = events(res)
    assert evs[0]["type"] == "delta"
    done = evs[-1]
    assert done["type"] == "done"
    assert done["text"] == "The contract renews for 12 months."
    assert done["citations"][0]["clause_refs"]

    assert seen["system"] == drafting.DRAFTING_SYSTEM_PROMPT
    content = model.calls[0][-1]["content"]
    assert content[0]["type"] == "document"
    instruction = content[-1]["text"]
    assert "notice of non-renewal" in instruction
    assert "Acme Supplies Ltd" in instruction  # addressed to the counterparty
    assert "Client A Ltd, by its General Counsel" in instruction
    assert "90 calendar days" in instruction  # the deadline's derivation
    assert "Keep it short." in instruction

    # Viewers can't draft; unknown deadlines are rejected.
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    assert (
        client_as(BOB)
        .post(
            f"/organizations/{org_id}/contracts/{contract_id}/draft-notice",
            json={"kind": "termination"},
        )
        .status_code
        == 404
    )
    res = alice.post(
        f"/organizations/{org_id}/contracts/{contract_id}/draft-notice",
        json={"kind": "termination", "deadline_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 404


def test_render_docx(client_as: Client, setup: tuple[str, str, str]) -> None:
    import docx

    org_id, _, _ = setup
    res = client_as(ALICE).post(
        f"/organizations/{org_id}/render-docx",
        json={
            "title": "Notice of non-renewal / MSA",
            "text": "Dear Sirs,\n\nWe give notice.\nRegards",
        },
    )
    assert res.status_code == 200
    assert 'filename="Notice_of_non-renewal__MSA.docx"' in res.headers["content-disposition"]
    paragraphs = [p.text for p in docx.Document(io.BytesIO(res.content)).paragraphs]
    assert paragraphs == ["Dear Sirs,", "We give notice.\nRegards"]


def test_excel_exports_respect_access(client_as: Client, setup: tuple[str, str, str]) -> None:
    org_id, _, _ = setup
    alice = client_as(ALICE)
    other_ws = create_workspace(client_as, org_id, "Client B Ltd")
    upload(alice, org_id, other_ws, msa_docx(extra="Side letter."))

    res = alice.get(f"/organizations/{org_id}/exports/contracts.xlsx")
    assert res.status_code == 200
    sheet = load_workbook(io.BytesIO(res.content)).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][:3] == ("Contract", "Workspace", "Counterparty")
    assert sorted(r[1] for r in rows[1:]) == ["Client A Ltd", "Client B Ltd"]

    res = alice.get(f"/organizations/{org_id}/exports/deadlines.xlsx")
    rows = list(load_workbook(io.BytesIO(res.content)).active.iter_rows(values_only=True))
    assert rows[0][0] == "Due date"
    assert {r[6] for r in rows[1:]} == {"Client A Ltd", "Client B Ltd"}
    assert any("90 calendar days" in (r[12] or "") for r in rows[1:])
    assert all(r[11] == ALICE for r in rows[1:])  # owner column

    # A member only exports the workspaces they belong to.
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{other_ws}/members",
        json={"email": BOB, "role": "viewer"},
    )
    rows = list(
        load_workbook(
            io.BytesIO(
                client_as(BOB).get(f"/organizations/{org_id}/exports/contracts.xlsx").content
            )
        ).active.iter_rows(values_only=True)
    )
    assert [r[1] for r in rows[1:]] == ["Client B Ltd"]
