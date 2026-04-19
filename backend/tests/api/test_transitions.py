"""API tests for cycle transitions (Phase 3 surface).

These tests live at the HTTP layer; the deeper logic is covered in
tests/unit/test_cycle_service.py.
"""

from __future__ import annotations


async def _create(authed_client, title: str, category: str = "personal") -> dict:
    r = await authed_client.post("/api/tasks", json={"category": category, "title": title})
    assert r.status_code == 201, r.text
    return r.json()["task"]


async def _current(authed_client, category: str = "personal") -> dict:
    r = await authed_client.get("/api/cycles/current", params={"category": category})
    assert r.status_code == 200
    return r.json()["cycle"]


async def test_transition_full_flow(authed_client):
    a = await _create(authed_client, "A")
    b = await _create(authed_client, "B")
    c = await _create(authed_client, "C")
    cycle = await _current(authed_client)

    r = await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={
            "actions": [
                {"persistent_task_id": a["persistent_task_id"], "action": "forward"},
                {"persistent_task_id": b["persistent_task_id"], "action": "complete"},
                {"persistent_task_id": c["persistent_task_id"], "action": "cancel"},
            ]
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"] == {"forwarded": 1, "completed": 1, "canceled": 1}
    assert body["new_cycle"]["ended_at"] is None

    # New cycle should hold one open task — A — with same display_id.
    new = await _current(authed_client)
    assert new["id"] == body["new_cycle"]["id"]
    detail = await authed_client.get("/api/cycles/current", params={"category": "personal"})
    open_tasks = detail.json()["tasks"]["open"]
    assert len(open_tasks) == 1
    assert open_tasks[0]["title"] == "A"
    assert open_tasks[0]["display_id"] == a["display_id"]
    assert open_tasks[0]["push_forward_count"] == 1


async def test_transition_empty_cycle(authed_client):
    cycle = await _current(authed_client)
    r = await authed_client.post(f"/api/cycles/{cycle['id']}/transition", json={"actions": []})
    assert r.status_code == 201
    assert r.json()["summary"] == {"forwarded": 0, "completed": 0, "canceled": 0}


async def test_transition_missing_action_returns_400(authed_client):
    a = await _create(authed_client, "A")
    b = await _create(authed_client, "B")
    cycle = await _current(authed_client)
    r = await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={
            "actions": [
                {"persistent_task_id": a["persistent_task_id"], "action": "forward"},
                # b deliberately omitted.
            ]
        },
    )
    assert r.status_code == 400


async def test_transition_extra_action_returns_400(authed_client):
    a = await _create(authed_client, "A")
    cycle = await _current(authed_client)
    fake_pid = "00000000-0000-0000-0000-000000000000"
    r = await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={
            "actions": [
                {"persistent_task_id": a["persistent_task_id"], "action": "forward"},
                {"persistent_task_id": fake_pid, "action": "complete"},
            ]
        },
    )
    assert r.status_code == 400


async def test_transition_double_call_returns_409(authed_client):
    a = await _create(authed_client, "A")
    cycle = await _current(authed_client)
    pid = a["persistent_task_id"]
    first = await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={"actions": [{"persistent_task_id": pid, "action": "forward"}]},
    )
    assert first.status_code == 201
    again = await authed_client.post(f"/api/cycles/{cycle['id']}/transition", json={"actions": []})
    assert again.status_code == 409


async def test_historical_task_patch_rejected(authed_client):
    a = await _create(authed_client, "A")
    cycle = await _current(authed_client)
    await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={"actions": [{"persistent_task_id": a["persistent_task_id"], "action": "complete"}]},
    )
    # The OLD row (a["id"]) is now in a closed cycle. PATCH should 403.
    r = await authed_client.patch(f"/api/tasks/{a['id']}", json={"title": "Hacked"})
    assert r.status_code == 403
