import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal, set_tenant
from app.models import Contract, ExtractionRun
from app.pipeline import extract as ext
from tests.conftest import Client
from tests.samples import FakeExtractor, blank_pdf, msa_docx, msa_pdf
from tests.test_api import ALICE, BOB, create_org, create_workspace

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeExtractor]:
    """AI switched on, with a deterministic stand-in for Claude."""
    extractor = FakeExtractor()
    monkeypatch.setattr(ext, "get_extractor", lambda: extractor)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    yield extractor


def upload(client, org_id: str, ws_id: str, data: bytes, name: str = "msa.docx"):  # type: ignore[no-untyped-def]
    return client.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/contracts",
        files={"file": (name, data, DOCX if name.endswith(".docx") else "application/pdf")},
    )


@pytest.fixture
def setup(client_as: Client) -> tuple[str, str]:
    org_id = create_org(client_as)
    client_as(ALICE).patch(f"/organizations/{org_id}", json={"default_country": "GB"})
    ws_id = create_workspace(client_as, org_id, "Client A Ltd")
    return org_id, ws_id


def test_upload_extracts_terms_rules_and_deadlines(
    client_as: Client, setup: tuple[str, str], fake: FakeExtractor
) -> None:
    org_id, ws_id = setup
    alice = client_as(ALICE)
    res = upload(alice, org_id, ws_id, msa_docx())
    assert res.status_code == 201, res.text
    contract_id = res.json()["id"]

    detail = alice.get(f"/organizations/{org_id}/contracts/{contract_id}").json()
    assert detail["status"] == "needs_review"
    assert detail["documents"][0]["status"] == "ready"
    assert detail["documents"][0]["text_source"] == "docx"
    assert detail["title"] == "Master Services Agreement"
    assert detail["counterparty_name"] == "Acme Supplies Ltd"
    assert detail["effective_date"] == "2025-01-01"
    assert (detail["initial_term_amount"], detail["initial_term_unit"]) == (24, "months")
    assert detail["auto_renews"] is True
    assert detail["currency"] == "EUR"
    assert detail["field_sources"]["effective_date"]["status"] == "ai_suggested"
    assert detail["pending_review"] == 3  # terms + 1 rule + 1 payment term

    # The workspace/org names are passed as context so the model can tell the sides apart.
    assert "Client A Ltd" in fake.last_context
    assert '<clause ref="C1"' in fake.last_xml

    (rule,) = detail["date_rules"]
    assert rule["offset_amount"] == 90 and rule["delivery_amount"] == 2
    assert "C999" not in rule["source_clause_refs"]  # unknown refs are dropped
    assert len(rule["source_clause_refs"]) == 2

    kinds = {d["kind"] for d in detail["deadlines"]}
    assert kinds == {"term_end", "notice", "payment"}
    notice = next(d for d in detail["deadlines"] if d["kind"] == "notice")
    assert date.fromisoformat(notice["due_date"]) >= date.today()
    assert any("90 calendar days" in s for s in notice["derivation"])
    assert notice["confirmed"] is False

    clauses = alice.get(
        f"/organizations/{org_id}/documents/{detail['documents'][0]['id']}/clauses"
    ).json()
    refs = {c["ref"]: c for c in clauses}
    assert all(r in refs for r in rule["source_clause_refs"])
    assert refs[rule["source_clause_refs"][0]]["number"] == "2.2"

    with SessionLocal() as db:
        set_tenant(db, uuid.UUID(org_id))
        run = db.scalars(select(ExtractionRun)).one()
        assert (run.status, run.model, run.input_tokens) == ("succeeded", "fake-model", 1000)


def test_pdf_upload_and_ocr_for_scans(
    client_as: Client, setup: tuple[str, str], fake: FakeExtractor
) -> None:
    org_id, ws_id = setup
    alice = client_as(ALICE)
    text_pdf = upload(alice, org_id, ws_id, msa_pdf(), "msa.pdf").json()
    detail = alice.get(f"/organizations/{org_id}/contracts/{text_pdf['id']}").json()
    assert detail["documents"][0]["page_count"] == 2
    assert detail["documents"][0]["text_source"] == "text_layer"
    assert fake.ocr_calls == 0

    scan = upload(alice, org_id, ws_id, blank_pdf(), "scan.pdf").json()
    detail = alice.get(f"/organizations/{org_id}/contracts/{scan['id']}").json()
    assert detail["documents"][0]["text_source"] == "ocr"
    assert fake.ocr_calls == 1
    assert detail["effective_date"] == "2025-01-01"


def test_review_flow(client_as: Client, setup: tuple[str, str], fake: FakeExtractor) -> None:
    org_id, ws_id = setup
    alice = client_as(ALICE)
    contract_id = upload(alice, org_id, ws_id, msa_docx()).json()["id"]
    base = f"/organizations/{org_id}"
    detail = alice.get(f"{base}/contracts/{contract_id}").json()

    # Edit a field: it becomes "edited" and survives a re-run of the AI.
    res = alice.patch(f"{base}/contracts/{contract_id}", json={"counterparty_name": "Acme plc"})
    assert res.status_code == 200
    assert res.json()["field_sources"]["counterparty_name"]["status"] == "edited"

    res = alice.post(f"{base}/contracts/{contract_id}/confirm-terms")
    assert res.json()["status"] == "active"
    assert res.json()["field_sources"]["effective_date"]["status"] == "confirmed"
    term_end = next(d for d in res.json()["deadlines"] if d["kind"] == "term_end")
    assert term_end["confirmed"] is True

    # Confirm the notice rule.
    rule_id = detail["date_rules"][0]["id"]
    res = alice.patch(f"{base}/date-rules/{rule_id}", json={"review_status": "confirmed"})
    assert res.json()["review_status"] == "confirmed"

    # Reject the payment term: its deadlines disappear.
    term_id = detail["payment_terms"][0]["id"]
    alice.patch(f"{base}/payment-terms/{term_id}", json={"review_status": "rejected"})
    detail = alice.get(f"{base}/contracts/{contract_id}").json()
    assert not [d for d in detail["deadlines"] if d["kind"] == "payment"]
    assert detail["pending_review"] == 0

    # Editing a rule marks it edited and recomputes.
    res = alice.patch(f"{base}/date-rules/{rule_id}", json={"offset_amount": 60})
    assert res.json()["review_status"] == "edited"
    detail = alice.get(f"{base}/contracts/{contract_id}").json()
    notice = next(d for d in detail["deadlines"] if d["kind"] == "notice")
    assert any("60 calendar days" in s for s in notice["derivation"])
    assert notice["confirmed"] is True

    # Add a manual rule and payment term.
    res = alice.post(
        f"{base}/contracts/{contract_id}/date-rules",
        json={
            "rule_type": "price_review",
            "label": "Annual price review",
            "anchor": "fixed_date",
            "fixed_date": "2027-01-01",
        },
    )
    assert res.status_code == 201 and res.json()["review_status"] == "confirmed"
    res = alice.post(
        f"{base}/contracts/{contract_id}/payment-terms",
        json={"description": "Setup", "frequency": "one_off", "first_due_date": "2027-02-01"},
    )
    assert res.status_code == 201

    # Re-running the AI keeps reviewed values and items.
    alice.post(f"{base}/contracts/{contract_id}/reprocess")
    detail = alice.get(f"{base}/contracts/{contract_id}").json()
    assert detail["counterparty_name"] == "Acme plc"
    assert fake.calls == 2
    statuses = sorted(r["review_status"] for r in detail["date_rules"])
    # The edited and manual rules are kept; the AI's notice rule is not suggested again
    # because the user already reviewed one, and the rejected payment term stays rejected.
    assert statuses == ["confirmed", "edited"]
    assert sorted(p["review_status"] for p in detail["payment_terms"]) == [
        "confirmed",
        "rejected",
    ]
    assert detail["pending_review"] == 0


def test_deadline_status_and_org_wide_list(
    client_as: Client, setup: tuple[str, str], fake: FakeExtractor
) -> None:
    org_id, ws_id = setup
    alice = client_as(ALICE)
    other_ws = create_workspace(client_as, org_id, "Client B Ltd")
    upload(alice, org_id, ws_id, msa_docx())
    upload(alice, org_id, other_ws, msa_docx(extra="Side letter."))

    deadlines = alice.get(f"/organizations/{org_id}/deadlines").json()
    assert {d["workspace_name"] for d in deadlines} == {"Client A Ltd", "Client B Ltd"}
    dates = [d["due_date"] for d in deadlines]
    assert dates == sorted(dates)

    # Bob only sees the workspace he belongs to.
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{other_ws}/members",
        json={"email": BOB, "role": "viewer"},
    )
    bob = client_as(BOB)
    bob_deadlines = bob.get(f"/organizations/{org_id}/deadlines").json()
    assert {d["workspace_name"] for d in bob_deadlines} == {"Client B Ltd"}
    assert bob.get(f"/organizations/{org_id}/deadlines?workspace_id={ws_id}").status_code == 404

    # Viewers can't change deadlines; editors can, and the status survives recomputation.
    target = bob_deadlines[0]
    res = bob.patch(f"/organizations/{org_id}/deadlines/{target['id']}", json={"status": "done"})
    assert res.status_code == 403
    res = alice.patch(f"/organizations/{org_id}/deadlines/{target['id']}", json={"status": "done"})
    assert res.json()["status"] == "done"
    alice.patch(f"/organizations/{org_id}/contracts/{target['contract_id']}", json={"title": "X"})
    remaining = alice.get(f"/organizations/{org_id}/deadlines?include_closed=true").json()
    same = [
        d
        for d in remaining
        if d["contract_id"] == target["contract_id"]
        and d["kind"] == target["kind"]
        and d["due_date"] == target["due_date"]
    ]
    assert same and same[0]["status"] == "done"


def test_permissions_and_validation(
    client_as: Client, setup: tuple[str, str], fake: FakeExtractor
) -> None:
    org_id, ws_id = setup
    alice = client_as(ALICE)
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/members",
        json={"email": BOB, "role": "viewer"},
    )
    bob = client_as(BOB)
    assert upload(bob, org_id, ws_id, msa_docx()).status_code == 403

    original = msa_docx()
    contract_id = upload(alice, org_id, ws_id, original).json()["id"]
    assert upload(alice, org_id, ws_id, original).status_code == 409  # duplicate
    assert upload(alice, org_id, ws_id, b"hello", "notes.txt").status_code == 415

    # Viewer can read but not edit.
    assert bob.get(f"/organizations/{org_id}/contracts/{contract_id}").status_code == 200
    assert (
        bob.patch(
            f"/organizations/{org_id}/contracts/{contract_id}", json={"title": "x"}
        ).status_code
        == 403
    )

    # Outsiders see nothing.
    outsider = client_as("eve@example.com")
    assert outsider.get(f"/organizations/{org_id}/contracts/{contract_id}").status_code == 404

    # Download the original file.
    doc_id = alice.get(f"/organizations/{org_id}/contracts/{contract_id}").json()["documents"][0][
        "id"
    ]
    res = bob.get(f"/organizations/{org_id}/documents/{doc_id}/file")
    assert res.status_code == 200
    assert res.content == msa_docx() or res.content[:2] == b"PK"

    # Delete.
    assert alice.delete(f"/organizations/{org_id}/contracts/{contract_id}").status_code == 204
    assert alice.get(f"/organizations/{org_id}/contracts/{contract_id}").status_code == 404


def test_upload_without_ai_keeps_document_and_clauses(
    client_as: Client, setup: tuple[str, str]
) -> None:
    org_id, ws_id = setup
    alice = client_as(ALICE)
    assert alice.get("/config").json() == {"ai_enabled": False}
    contract_id = upload(alice, org_id, ws_id, msa_docx()).json()["id"]
    detail = alice.get(f"/organizations/{org_id}/contracts/{contract_id}").json()
    document = detail["documents"][0]
    assert (document["status"], document["ai_status"], document["error"]) == (
        "ready",
        "skipped",
        None,
    )
    assert detail["status"] == "needs_review"  # the user enters the terms
    assert detail["deadlines"] == [] and detail["date_rules"] == []
    clauses = alice.get(f"/organizations/{org_id}/documents/{document['id']}/clauses").json()
    assert any(c["number"] == "2.2" for c in clauses)

    # Scanned PDFs can't be read without AI, but the file is kept.
    scan = upload(alice, org_id, ws_id, blank_pdf(), "scan.pdf").json()
    doc = alice.get(f"/organizations/{org_id}/contracts/{scan['id']}").json()["documents"][0]
    assert (doc["status"], doc["ai_status"], doc["text_source"]) == (
        "ready",
        "skipped",
        "needs_ocr",
    )


def test_ai_errors_are_reported(
    client_as: Client, setup: tuple[str, str], fake: FakeExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, ws_id = setup

    def boom(xml: str, context: str) -> None:
        raise ext.ExtractionError("The AI model declined to process this document")

    monkeypatch.setattr(fake, "extract", boom)
    contract_id = upload(client_as(ALICE), org_id, ws_id, msa_docx()).json()["id"]
    detail = client_as(ALICE).get(f"/organizations/{org_id}/contracts/{contract_id}").json()
    document = detail["documents"][0]
    assert (document["status"], document["ai_status"]) == ("failed", "failed")
    assert document["error"] == "The AI model declined to process this document"
    assert detail["status"] == "needs_review"


def test_contracts_are_isolated_by_rls(
    client_as: Client, setup: tuple[str, str], fake: FakeExtractor
) -> None:
    org_id, ws_id = setup
    upload(client_as(ALICE), org_id, ws_id, msa_docx())
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Contract)) == 0
        db.commit()
        set_tenant(db, uuid.UUID(org_id))
        assert db.scalar(select(func.count()).select_from(Contract)) == 1
