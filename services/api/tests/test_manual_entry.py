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


def test_list_contracts_across_workspaces(client_as: Client) -> None:
    org_id, ws_a = setup(client_as)
    alice = client_as(ALICE)
    ws_b = create_workspace(client_as, org_id, "Client B Ltd")
    for ws, title in ((ws_a, "A contract"), (ws_b, "B contract")):
        alice.post(
            f"/organizations/{org_id}/workspaces/{ws}/contracts/manual",
            json={**MANUAL, "title": title},
        )
    everything = alice.get(f"/organizations/{org_id}/contracts").json()
    assert {(c["title"], c["workspace_name"]) for c in everything} == {
        ("A contract", "Client A Ltd"),
        ("B contract", "Client B Ltd"),
    }
    assert all(c["next_deadline"] for c in everything)
    # Payments come first by date, but the next date to decide on is shown.
    assert all(c["next_deadline"]["kind"] != "payment" for c in everything)
    only_b = alice.get(f"/organizations/{org_id}/contracts", params={"workspace_id": ws_b})
    assert [c["title"] for c in only_b.json()] == ["B contract"]

    # A member only sees the workspaces they belong to.
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    alice.post(
        f"/organizations/{org_id}/workspaces/{ws_a}/members", json={"email": BOB, "role": "viewer"}
    )
    bob = client_as(BOB)
    assert [c["title"] for c in bob.get(f"/organizations/{org_id}/contracts").json()] == [
        "A contract"
    ]
    assert (
        bob.get(f"/organizations/{org_id}/contracts", params={"workspace_id": ws_b}).status_code
        == 404
    )


def test_a_company_starts_with_one_workspace(client_as: Client) -> None:
    alice = client_as(ALICE)
    company = alice.post("/organizations", json={"name": "Acme Ltd", "kind": "company"}).json()
    firm = alice.post("/organizations", json={"name": "Law & Co", "kind": "law_firm"}).json()
    (ws,) = alice.get(f"/organizations/{company['id']}/workspaces").json()
    assert (ws["name"], ws["kind"], ws["my_role"]) == ("Acme Ltd", "department", "admin")
    # Firms and holdings add their clients or companies themselves.
    assert alice.get(f"/organizations/{firm['id']}/workspaces").json() == []


def test_sample_contract(client_as: Client) -> None:
    org_id, ws_id = setup(client_as)
    alice = client_as(ALICE)
    res = alice.post(f"/organizations/{org_id}/workspaces/{ws_id}/contracts/sample")
    assert res.status_code == 201, res.text
    c = alice.get(f"/organizations/{org_id}/contracts/{res.json()['id']}").json()
    assert c["title"].startswith("Sample:")
    (doc,) = c["documents"]
    assert doc["status"] == "ready"  # split into clauses for reading
    clauses = alice.get(f"/organizations/{org_id}/documents/{doc['id']}/clauses").json()
    assert any("14 days" in cl["text"] for cl in clauses)
    # The notice deadline is always a few weeks away, so the home page has something to show.
    notice = next(d for d in c["deadlines"] if d["kind"] == "notice")
    days = (date.fromisoformat(notice["due_date"]) - date.today()).days
    assert 7 <= days <= 31, days
    assert c["next_deadline"]["kind"] == "notice"
    # A second sample is fine (e.g. after deleting the first one or in another workspace).
    again = alice.post(f"/organizations/{org_id}/workspaces/{ws_id}/contracts/sample")
    assert again.status_code == 201
