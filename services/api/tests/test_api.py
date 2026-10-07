import uuid

from sqlalchemy import func, select

from app.db import SessionLocal, set_tenant
from app.models import Workspace
from tests.conftest import Client

ALICE = "alice@example.com"
BOB = "bob@example.com"
CAROL = "carol@example.com"


def create_org(client_as: Client, email: str = ALICE, name: str = "Acme Legal") -> str:
    res = client_as(email).post("/organizations", json={"name": name, "kind": "law_firm"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def create_workspace(client_as: Client, org_id: str, name: str, email: str = ALICE) -> str:
    res = client_as(email).post(
        f"/organizations/{org_id}/workspaces", json={"name": name, "kind": "client"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_requires_authentication(client_as: Client) -> None:
    res = client_as("x@example.com")
    res.headers.pop("X-Dev-User-Email")
    assert res.get("/me").status_code == 401


def test_me_provisions_user_and_lists_orgs(client_as: Client) -> None:
    res = client_as("Alice@Example.com").get("/me")
    assert res.status_code == 200
    assert res.json()["user"]["email"] == ALICE
    assert res.json()["organizations"] == []

    org_id = create_org(client_as)
    orgs = client_as(ALICE).get("/me").json()["organizations"]
    assert [(o["organization"]["id"], o["role"]) for o in orgs] == [(org_id, "owner")]


def test_validation(client_as: Client) -> None:
    alice = client_as(ALICE)
    bad_tz = {"name": "X", "kind": "company", "default_timezone": "Mars/Base"}
    assert alice.post("/organizations", json=bad_tz).status_code == 422
    bad_country = {"name": "X", "kind": "company", "default_country": "GBR"}
    assert alice.post("/organizations", json=bad_country).status_code == 422


def test_non_members_cannot_see_organization(client_as: Client) -> None:
    org_id = create_org(client_as)
    bob = client_as(BOB)
    assert bob.get(f"/organizations/{org_id}").status_code == 404
    assert bob.get(f"/organizations/{org_id}/workspaces").status_code == 404


def test_workspace_access_is_limited_to_members(client_as: Client) -> None:
    org_id = create_org(client_as)
    client_a = create_workspace(client_as, org_id, "Client A")
    client_b = create_workspace(client_as, org_id, "Client B")

    alice = client_as(ALICE)
    assert (
        alice.post(
            f"/organizations/{org_id}/members", json={"email": BOB, "role": "member"}
        ).status_code
        == 201
    )

    bob = client_as(BOB)
    # Org member without workspace memberships sees nothing.
    assert bob.get(f"/organizations/{org_id}/workspaces").json() == []
    assert bob.get(f"/organizations/{org_id}/workspaces/{client_a}").status_code == 404

    res = alice.post(
        f"/organizations/{org_id}/workspaces/{client_a}/members",
        json={"email": BOB, "role": "viewer"},
    )
    assert res.status_code == 201, res.text

    listed = bob.get(f"/organizations/{org_id}/workspaces").json()
    assert [(w["id"], w["my_role"]) for w in listed] == [(client_a, "viewer")]
    assert bob.get(f"/organizations/{org_id}/workspaces/{client_b}").status_code == 404

    # Viewers cannot modify the workspace or create workspaces.
    assert (
        bob.patch(
            f"/organizations/{org_id}/workspaces/{client_a}", json={"name": "Renamed"}
        ).status_code
        == 403
    )
    assert (
        bob.post(
            f"/organizations/{org_id}/workspaces", json={"name": "Mine", "kind": "client"}
        ).status_code
        == 403
    )


def test_workspace_member_must_belong_to_org(client_as: Client) -> None:
    org_id = create_org(client_as)
    ws = create_workspace(client_as, org_id, "Client A")
    res = client_as(ALICE).post(
        f"/organizations/{org_id}/workspaces/{ws}/members", json={"email": CAROL}
    )
    assert res.status_code == 400


def test_nested_workspaces(client_as: Client) -> None:
    org_id = create_org(client_as, name="Holding")
    parent = create_workspace(client_as, org_id, "Holding AG")
    res = client_as(ALICE).post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Sub GmbH", "kind": "entity", "parent_workspace_id": parent},
    )
    assert res.status_code == 201
    assert res.json()["parent_workspace_id"] == parent

    other_org = create_org(client_as, email=BOB, name="Other")
    foreign = create_workspace(client_as, other_org, "Foreign", email=BOB)
    res = client_as(ALICE).post(
        f"/organizations/{org_id}/workspaces",
        json={"name": "Bad", "kind": "entity", "parent_workspace_id": foreign},
    )
    assert res.status_code == 404


def test_cannot_remove_last_owner(client_as: Client) -> None:
    org_id = create_org(client_as)
    alice = client_as(ALICE)
    members = alice.get(f"/organizations/{org_id}/members").json()
    owner_id = members[0]["id"]
    assert alice.delete(f"/organizations/{org_id}/members/{owner_id}").status_code == 409
    assert (
        alice.patch(
            f"/organizations/{org_id}/members/{owner_id}", json={"role": "admin"}
        ).status_code
        == 409
    )


def test_admins_cannot_promote_to_owner(client_as: Client) -> None:
    org_id = create_org(client_as)
    alice = client_as(ALICE)
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB, "role": "admin"})
    res = client_as(BOB).post(
        f"/organizations/{org_id}/members", json={"email": CAROL, "role": "owner"}
    )
    assert res.status_code == 403


def test_removing_org_member_removes_workspace_access(client_as: Client) -> None:
    org_id = create_org(client_as)
    ws = create_workspace(client_as, org_id, "Client A")
    alice = client_as(ALICE)
    member = alice.post(f"/organizations/{org_id}/members", json={"email": BOB}).json()
    alice.post(f"/organizations/{org_id}/workspaces/{ws}/members", json={"email": BOB})
    assert alice.delete(f"/organizations/{org_id}/members/{member['id']}").status_code == 204
    assert alice.get(f"/organizations/{org_id}/workspaces/{ws}/members").json() == []


def test_invited_user_is_linked_on_first_login(client_as: Client) -> None:
    org_id = create_org(client_as)
    client_as(ALICE).post(f"/organizations/{org_id}/members", json={"email": BOB})
    orgs = client_as(BOB).get("/me").json()["organizations"]
    assert [o["organization"]["id"] for o in orgs] == [org_id]


def test_audit_trail(client_as: Client) -> None:
    org_id = create_org(client_as)
    create_workspace(client_as, org_id, "Client A")
    events = client_as(ALICE).get(f"/organizations/{org_id}/audit-events").json()
    assert [e["action"] for e in events] == ["workspace.created", "organization.created"]


def test_row_level_security_isolates_tenants(client_as: Client) -> None:
    org_a = create_org(client_as)
    create_workspace(client_as, org_a, "A1")
    org_b = create_org(client_as, email=BOB, name="Other firm")
    create_workspace(client_as, org_b, "B1", email=BOB)
    create_workspace(client_as, org_b, "B2", email=BOB)

    with SessionLocal() as db:
        count = select(func.count()).select_from(Workspace)
        assert db.scalar(count) == 0  # no tenant set → nothing visible
        db.commit()
        set_tenant(db, uuid.UUID(org_a))
        assert db.scalar(count) == 1
        db.commit()
        set_tenant(db, uuid.UUID(org_b))
        assert db.scalar(count) == 2

        # Writing into another tenant is rejected by the policy's WITH CHECK.
        db.add(Workspace(organization_id=uuid.UUID(org_a), name="Sneaky", kind="client"))
        try:
            db.flush()
            raise AssertionError("cross-tenant insert should fail")
        except Exception as exc:  # noqa: BLE001
            assert "row-level security" in str(exc)
        db.rollback()


def test_notice_preview(client_as: Client) -> None:
    res = client_as(ALICE).post(
        "/deadlines/notice-preview",
        json={
            "effective_date": "2025-01-01",
            "initial_term": {"amount": 24, "unit": "months"},
            "renewal_term": {"amount": 12, "unit": "months"},
            "notice_period": {"amount": 90, "unit": "days"},
            "calendar": {"country": "GB", "subdivision": "ENG"},
            "as_of": "2026-09-01",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["notice_deadline"] == "2026-10-02"
    assert body["days_left"] == 31
    assert body["term"] == {"number": 1, "start": "2025-01-01", "end": "2026-12-31"}

    bad = client_as(ALICE).post(
        "/deadlines/notice-preview",
        json={
            "effective_date": "2025-01-01",
            "initial_term": {"amount": 1, "unit": "months", "basis": "business"},
            "notice_period": {"amount": 90, "unit": "days"},
        },
    )
    assert bad.status_code == 422
