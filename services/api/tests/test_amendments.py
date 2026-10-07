from typing import Any

from tests.conftest import Client
from tests.samples import msa_docx
from tests.test_api import ALICE, BOB, create_org, create_workspace
from tests.test_contracts import DOCX
from tests.test_manual_entry import MANUAL


def setup(client_as: Client) -> tuple[str, str, dict[str, Any]]:
    org_id = create_org(client_as)
    ws_id = create_workspace(client_as, org_id, "Client A Ltd")
    contract = (
        client_as(ALICE)
        .post(f"/organizations/{org_id}/workspaces/{ws_id}/contracts/manual", json=MANUAL)
        .json()
    )
    return org_id, ws_id, contract


def deadline(detail: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(d for d in detail["deadlines"] if d["kind"] == kind)


def test_amendment_changes_terms_and_deadlines(client_as: Client) -> None:
    org_id, _, c = setup(client_as)
    alice = client_as(ALICE)
    base = f"/organizations/{org_id}"
    rule_id = c["date_rules"][0]["id"]
    payment_id = c["payment_terms"][0]["id"]
    before_term_end = deadline(c, "term_end")["due_date"]

    res = alice.post(
        f"{base}/contracts/{c['id']}/amendments",
        json={
            "title": "Amendment No. 1",
            "effective_date": "2026-06-01",
            "signed_date": "2026-05-20",
            "description": "Extends the initial term and shortens the notice period.",
            "contract": {"initial_term_amount": 36, "contract_value": "24000"},
            "date_rules": [{"date_rule_id": rule_id, "offset_amount": 1}],
            "payment_terms": [{"payment_term_id": payment_id, "amount": "1650"}],
            "new_payment_terms": [
                {
                    "description": "Annual deep clean",
                    "frequency": "annual",
                    "first_due_date": "2026-07-01",
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    amendment = res.json()
    changes = {(ch["target_type"], ch["field"]): ch for ch in amendment["changes"]}
    assert changes[("contract", "initial_term_amount")]["old_value"] == 24
    assert changes[("contract", "initial_term_amount")]["new_value"] == 36
    assert changes[("date_rule", "offset_amount")]["old_value"] == 3
    assert changes[("payment_term", "amount")]["new_value"] == "1650"
    assert changes[("payment_term", "_created")]["label"] == "Annual deep clean"
    assert len(amendment["changes"]) == 5

    detail = alice.get(f"{base}/contracts/{c['id']}").json()
    assert detail["initial_term_amount"] == 36
    assert detail["contract_value"] == "24000.00"
    source = detail["field_sources"]["initial_term"]
    assert (source["status"], source["amendment_title"]) == ("amended", "Amendment No. 1")
    assert [a["title"] for a in detail["amendments"]] == ["Amendment No. 1"]
    # Term now ends 31 Dec 2027; the notice deadline is 1 month before.
    assert deadline(detail, "term_end")["due_date"] != before_term_end
    notice = deadline(detail, "notice")
    assert any("1 month" in s for s in notice["derivation"])
    assert detail["date_rules"][0]["review_status"] == "confirmed"
    assert len(detail["payment_terms"]) == 2

    events = alice.get(f"{base}/audit-events").json()
    assert "contract.amended" in [e["action"] for e in events]


def test_deleting_an_amendment_reverts_it(client_as: Client) -> None:
    org_id, _, c = setup(client_as)
    alice = client_as(ALICE)
    base = f"/organizations/{org_id}"
    original_end = deadline(c, "term_end")["due_date"]
    first = alice.post(
        f"{base}/contracts/{c['id']}/amendments",
        json={
            "title": "Amendment No. 1",
            "contract": {"initial_term_amount": 36, "governing_law": "Scotland"},
            "new_date_rules": [
                {
                    "rule_type": "price_review",
                    "label": "Price review",
                    "anchor": "fixed_date",
                    "fixed_date": "2027-01-01",
                }
            ],
        },
    ).json()
    # A later edit to one of the amended values must survive the revert.
    alice.patch(f"{base}/contracts/{c['id']}", json={"governing_law": "England and Wales"})

    res = alice.delete(f"{base}/amendments/{first['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["reverted"] == 2
    assert body["conflicts"] == ["Contract: governing law"]

    detail = alice.get(f"{base}/contracts/{c['id']}").json()
    assert detail["initial_term_amount"] == 24
    assert detail["governing_law"] == "England and Wales"
    assert detail["amendments"] == []
    assert [r["label"] for r in detail["date_rules"]] == ["Notice of non-renewal"]
    assert deadline(detail, "term_end")["due_date"] == original_end
    assert detail["field_sources"]["initial_term"]["status"] == "edited"


def test_amendment_document_and_permissions(client_as: Client) -> None:
    org_id, ws_id, c = setup(client_as)
    alice = client_as(ALICE)
    base = f"/organizations/{org_id}"
    amendment = alice.post(
        f"{base}/contracts/{c['id']}/amendments", json={"title": "Amendment No. 1"}
    ).json()
    assert amendment["changes"] == []  # recording an amendment with no term changes is fine

    res = alice.post(
        f"{base}/amendments/{amendment['id']}/documents",
        files={"file": ("amendment-1.docx", msa_docx(), DOCX)},
    )
    assert res.status_code == 201
    (doc,) = res.json()["documents"]
    detail = alice.get(f"{base}/contracts/{c['id']}").json()
    assert detail["documents"] == []  # not shown as the contract's own document
    assert detail["amendments"][0]["documents"][0]["status"] == "ready"
    assert alice.get(f"{base}/documents/{doc['id']}/clauses").json()

    res = alice.patch(
        f"{base}/amendments/{amendment['id']}",
        json={"title": "First amendment", "effective_date": "2026-01-01"},
    )
    assert (res.json()["title"], res.json()["effective_date"]) == ("First amendment", "2026-01-01")

    # Validation: rules must belong to the contract.
    bad = alice.post(
        f"{base}/contracts/{c['id']}/amendments",
        json={
            "title": "X",
            "date_rules": [{"date_rule_id": "00000000-0000-0000-0000-000000000000"}],
        },
    )
    assert bad.status_code == 422

    # Viewers can't amend.
    alice.post(f"{base}/members", json={"email": BOB})
    alice.post(f"{base}/workspaces/{ws_id}/members", json={"email": BOB, "role": "viewer"})
    bob = client_as(BOB)
    assert (
        bob.post(f"{base}/contracts/{c['id']}/amendments", json={"title": "X"}).status_code == 403
    )
    assert bob.delete(f"{base}/amendments/{amendment['id']}").status_code == 403
