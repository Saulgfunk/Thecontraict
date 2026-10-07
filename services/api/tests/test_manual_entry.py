from datetime import date

from tests.conftest import Client
from tests.samples import FakeExtractor, msa_docx
from tests.test_api import ALICE, BOB, create_org, create_workspace
from tests.test_contracts import DOCX, fake  # noqa: F401  (fixture)

MANUAL = {
    "title": "Office cleaning agreement",
    "counterparty_name": "Sparkle Services Ltd",
    "contract_type": "Services",
    "effective_date": "2025-01-01",
    "initial_term_amount": 24,
    "initial_term_unit": "months",
    "auto_renews": True,
    "renewal_term_amount": 12,
    "renewal_term_unit": "months",
    "holiday_country": "gb",
    "currency": "gbp",
    "contract_value": "18000.00",
    "date_rules": [
        {
            "rule_type": "non_renewal_notice",
            "label": "Notice of non-renewal",
            "anchor": "term_end",
            "offset_amount": 3,
            "offset_unit": "months",
        }
    ],
    "payment_terms": [
        {
            "description": "Monthly cleaning fee",
            "direction": "payable",
            "amount": "1500",
            "frequency": "monthly",
            "first_due_date": "2025-01-31",
            "payment_days": 30,
        }
    ],
}


def setup(client_as: Client) -> tuple[str, str]:
    org_id = create_org(client_as)
    return org_id, create_workspace(client_as, org_id, "Client A Ltd")


def test_create_contract_manually(client_as: Client) -> None:
    org_id, ws_id = setup(client_as)
    alice = client_as(ALICE)
    res = alice.post(f"/organizations/{org_id}/workspaces/{ws_id}/contracts/manual", json=MANUAL)
    assert res.status_code == 201, res.text
    c = res.json()
    assert c["status"] == "active"
    assert c["reviewed_at"]
    assert (c["currency"], c["holiday_country"]) == ("GBP", "GB")
    assert c["documents"] == []
    assert c["field_sources"]["effective_date"]["status"] == "manual"
    assert "end_date" not in c["field_sources"]  # only fields actually entered
    assert c["pending_review"] == 0
    assert [r["review_status"] for r in c["date_rules"]] == ["confirmed"]

    kinds = {d["kind"] for d in c["deadlines"]}
    assert kinds == {"term_end", "notice", "payment"}
    assert all(d["confirmed"] for d in c["deadlines"])
    notice = next(d for d in c["deadlines"] if d["kind"] == "notice")
    assert date.fromisoformat(notice["due_date"]) >= date.today()

    audit = alice.get(f"/organizations/{org_id}/audit-events").json()
    assert "contract.created_manually" in [e["action"] for e in audit]


def test_manual_validation_and_permissions(client_as: Client) -> None:
    org_id, ws_id = setup(client_as)
    alice = client_as(ALICE)
    url = f"/organizations/{org_id}/workspaces/{ws_id}/contracts/manual"
    assert alice.post(url, json={"title": ""}).status_code == 422
    half = {"title": "X", "initial_term_amount": 12}
    res = alice.post(url, json=half)
    assert res.status_code == 422 and "initial term" in res.text
    assert alice.post(url, json={"title": "X", "holiday_country": "GBR"}).status_code == 422

    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/members", json={"email": BOB, "role": "viewer"}
    )
    assert client_as(BOB).post(url, json={"title": "X"}).status_code == 403


def test_attach_document_without_ai(client_as: Client) -> None:
    org_id, ws_id = setup(client_as)
    alice = client_as(ALICE)
    c = alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/contracts/manual", json=MANUAL
    ).json()
    signed = msa_docx()
    res = alice.post(
        f"/organizations/{org_id}/contracts/{c['id']}/documents",
        files={"file": ("signed.docx", signed, DOCX)},
    )
    assert res.status_code == 201
    detail = alice.get(f"/organizations/{org_id}/contracts/{c['id']}").json()
    (doc,) = detail["documents"]
    assert (doc["status"], doc["ai_status"]) == ("ready", "skipped")
    assert detail["status"] == "active"  # still active, terms unchanged
    assert detail["title"] == "Office cleaning agreement"
    clauses = alice.get(f"/organizations/{org_id}/documents/{doc['id']}/clauses").json()
    assert len(clauses) > 5

    # The same file can't be attached twice in a workspace.
    again = alice.post(
        f"/organizations/{org_id}/contracts/{c['id']}/documents",
        files={"file": ("signed.docx", signed, DOCX)},
    )
    assert again.status_code == 409


def test_ai_never_overwrites_manual_terms(client_as: Client, fake: FakeExtractor) -> None:  # noqa: F811
    org_id, ws_id = setup(client_as)
    alice = client_as(ALICE)
    c = alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/contracts/manual", json=MANUAL
    ).json()
    alice.post(
        f"/organizations/{org_id}/contracts/{c['id']}/documents",
        files={"file": ("signed.docx", msa_docx(), DOCX)},
    )
    detail = alice.get(f"/organizations/{org_id}/contracts/{c['id']}").json()
    assert fake.calls == 1
    assert detail["documents"][0]["ai_status"] == "analysed"
    # Typed-in values win over what the AI found in the (different) document.
    assert detail["title"] == "Office cleaning agreement"
    assert detail["counterparty_name"] == "Sparkle Services Ltd"
    assert detail["currency"] == "GBP"
    assert detail["effective_date"] == "2025-01-01"
    # Fields the user left empty are filled in as AI suggestions.
    assert detail["governing_law"] == "England and Wales"
    assert detail["field_sources"]["governing_law"]["status"] == "ai_suggested"
    # The confirmed notice rule isn't duplicated by the AI's suggestion of the same rule.
    assert [r["review_status"] for r in detail["date_rules"]] == ["confirmed"]
    assert detail["status"] == "active"
