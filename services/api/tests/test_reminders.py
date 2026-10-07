from datetime import date

import pytest
from icalendar import Calendar

from app import email
from app.reminders import send_due_reminders, send_weekly_digests
from tests.conftest import Client
from tests.samples import FakeExtractor, msa_docx
from tests.test_api import ALICE, BOB, create_org, create_workspace
from tests.test_contracts import fake, upload  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _clear_outbox() -> None:
    email.outbox.clear()


@pytest.fixture
def contract(client_as: Client, fake: FakeExtractor) -> tuple[str, str, str]:  # noqa: F811
    org_id = create_org(client_as)
    client_as(ALICE).patch(f"/organizations/{org_id}", json={"default_country": "GB"})
    ws_id = create_workspace(client_as, org_id, "Client A Ltd")
    contract_id = upload(client_as(ALICE), org_id, ws_id, msa_docx()).json()["id"]
    return org_id, ws_id, contract_id


def test_reminders_are_sent_once_and_survive_recalculation(
    client_as: Client, contract: tuple[str, str, str]
) -> None:
    org_id, _, contract_id = contract
    alice = client_as(ALICE)

    # Term ends 31 Dec 2026: on 7 Oct it is 85 days away, so the "90 days" point is reached.
    assert send_due_reminders(date(2026, 10, 7)) == 1
    (sent,) = email.outbox
    assert sent.to == ALICE
    assert "Term renews automatically" in sent.subject
    assert f"/app/{org_id}/contracts/{contract_id}" in sent.text
    assert "not yet confirmed" in sent.text

    # Running again, or after the deadlines are recalculated, sends nothing new.
    assert send_due_reminders(date(2026, 10, 7)) == 0
    alice.patch(f"/organizations/{org_id}/contracts/{contract_id}", json={"title": "MSA"})
    assert send_due_reminders(date(2026, 10, 8)) == 0
    assert len(email.outbox) == 1

    # Later: the term end reaches its 7-day point and January's payment its 7-day point.
    assert send_due_reminders(date(2026, 12, 28)) == 2
    batch = email.outbox[-1]
    assert batch.subject.startswith("2 contract deadlines coming up")

    notifications = alice.get(f"/organizations/{org_id}/notifications").json()
    assert notifications["unread_count"] == 3
    titles = [n["title"] for n in notifications["items"]]
    assert "Term renews automatically in 3 days" in titles
    first = notifications["items"][0]["id"]
    alice.post(f"/organizations/{org_id}/notifications/read", json={"ids": [first]})
    assert alice.get(f"/organizations/{org_id}/notifications").json()["unread_count"] == 2
    alice.post(f"/organizations/{org_id}/notifications/read", json={})
    assert alice.get(f"/organizations/{org_id}/notifications").json()["unread_count"] == 0


def test_done_deadlines_and_email_preferences(
    client_as: Client, contract: tuple[str, str, str]
) -> None:
    org_id, _, contract_id = contract
    alice = client_as(ALICE)
    term_end = next(
        d
        for d in alice.get(f"/organizations/{org_id}/contracts/{contract_id}").json()["deadlines"]
        if d["kind"] == "term_end"
    )
    alice.patch(f"/organizations/{org_id}/deadlines/{term_end['id']}", json={"status": "done"})
    assert send_due_reminders(date(2026, 10, 7)) == 0

    res = alice.patch(f"/organizations/{org_id}/me/preferences", json={"email_reminders": False})
    assert res.json() == {"email_reminders": False, "weekly_digest": True}
    assert send_due_reminders(date(2026, 12, 28)) == 1  # January payment
    assert email.outbox == []  # in-app only
    assert alice.get(f"/organizations/{org_id}/notifications").json()["unread_count"] == 1


def test_owner_receives_reminders(client_as: Client, contract: tuple[str, str, str]) -> None:
    org_id, ws_id, contract_id = contract
    alice = client_as(ALICE)
    bob_member = alice.post(f"/organizations/{org_id}/members", json={"email": BOB}).json()
    bob_id = bob_member["user"]["id"]

    # Bob can't own a contract he can't see.
    res = alice.patch(f"/organizations/{org_id}/contracts/{contract_id}", json={"owner_id": bob_id})
    assert res.status_code == 400

    alice.post(
        f"/organizations/{org_id}/workspaces/{ws_id}/members",
        json={"email": BOB, "role": "editor"},
    )
    res = alice.patch(f"/organizations/{org_id}/contracts/{contract_id}", json={"owner_id": bob_id})
    assert res.json()["owner_id"] == bob_id
    send_due_reminders(date(2026, 10, 7))
    assert [e.to for e in email.outbox] == [BOB]

    # If the owner loses access, the reminders fall back to the uploader.
    alice.delete(f"/organizations/{org_id}/members/{bob_member['id']}")
    send_due_reminders(date(2026, 12, 28))
    assert email.outbox[-1].to == ALICE


def test_weekly_digest(client_as: Client, contract: tuple[str, str, str]) -> None:
    org_id, _, _ = contract
    client_as(ALICE).post(f"/organizations/{org_id}/members", json={"email": BOB})
    assert send_weekly_digests(date(2026, 12, 7)) == 1  # Bob has no workspace access
    (digest,) = email.outbox
    assert digest.to == ALICE
    assert digest.subject == "Weekly contract digest: Acme Legal"
    assert "Term renews automatically" in digest.text
    assert "waiting for review" in digest.text

    client_as(ALICE).patch(f"/organizations/{org_id}/me/preferences", json={"weekly_digest": False})
    assert send_weekly_digests(date(2026, 12, 7)) == 0


def test_reminder_settings(client_as: Client, contract: tuple[str, str, str]) -> None:
    org_id, _, _ = contract
    alice = client_as(ALICE)
    settings = alice.get(f"/organizations/{org_id}/reminder-settings").json()["reminder_days"]
    assert settings["notice"][0] == 120

    res = alice.put(
        f"/organizations/{org_id}/reminder-settings",
        json={"reminder_days": {"term_end": [10, 100, 10]}},
    )
    assert res.json()["reminder_days"]["term_end"] == [100, 10]
    assert res.json()["reminder_days"]["notice"][0] == 120  # defaults for the rest

    # 85 days before the term end: the 100-day point applies now.
    send_due_reminders(date(2026, 10, 7))
    assert "Term renews automatically" in email.outbox[0].subject

    bad = alice.put(
        f"/organizations/{org_id}/reminder-settings", json={"reminder_days": {"x": [1]}}
    )
    assert bad.status_code == 422
    alice.post(f"/organizations/{org_id}/members", json={"email": BOB})
    denied = client_as(BOB).put(
        f"/organizations/{org_id}/reminder-settings", json={"reminder_days": {}}
    )
    assert denied.status_code == 403


def test_calendar_feed(client_as: Client, contract: tuple[str, str, str]) -> None:
    org_id, _, _ = contract
    alice = client_as(ALICE)
    assert alice.get(f"/organizations/{org_id}/calendar-feed").json()["active"] is False

    url = alice.post(f"/organizations/{org_id}/calendar-feed").json()["url"]
    path = url.split("8000", 1)[1]
    anonymous = client_as("nobody@example.com")
    anonymous.headers.pop("X-Dev-User-Email")
    res = anonymous.get(path)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/calendar")
    cal = Calendar.from_ical(res.content)
    summaries = [str(e["summary"]) for e in cal.walk("VEVENT")]
    assert any("Term renews automatically – Master Services Agreement" in s for s in summaries)
    assert alice.get(f"/organizations/{org_id}/calendar-feed").json()["last_accessed_at"]

    # Creating a new URL invalidates the old one; deleting removes the feed.
    new_url = alice.post(f"/organizations/{org_id}/calendar-feed").json()["url"]
    assert anonymous.get(path).status_code == 404
    new_path = new_url.split("8000", 1)[1]
    assert anonymous.get(new_path).status_code == 200
    alice.delete(f"/organizations/{org_id}/calendar-feed")
    assert anonymous.get(new_path).status_code == 404
