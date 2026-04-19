"""API tests for /api/history."""
from __future__ import annotations


async def test_history_empty(authed_client):
    r = await authed_client.get("/api/history", params={"category": "personal"})
    assert r.status_code == 200
    assert r.json() == {"cycles": [], "lineages": []}


async def test_history_after_one_transition(authed_client):
    # Create A and B; forward A, complete B.
    a = (
        await authed_client.post("/api/tasks", json={"category": "personal", "title": "A"})
    ).json()["task"]
    b = (
        await authed_client.post("/api/tasks", json={"category": "personal", "title": "B"})
    ).json()["task"]
    cycle = (
        await authed_client.get("/api/cycles/current", params={"category": "personal"})
    ).json()["cycle"]
    await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={
            "actions": [
                {"persistent_task_id": a["persistent_task_id"], "action": "forward"},
                {"persistent_task_id": b["persistent_task_id"], "action": "complete"},
            ]
        },
    )

    h = await authed_client.get("/api/history", params={"category": "personal"})
    assert h.status_code == 200
    body = h.json()
    assert len(body["cycles"]) == 2
    # Two lineages: A spans 2 cycles (forwarded), B spans 1 cycle (completed).
    by_title = {l["title"]: l for l in body["lineages"]}
    assert by_title["A"]["push_forward_count"] == 1
    assert by_title["A"]["latest_status"] == "open"
    assert len(by_title["A"]["spans"]) == 2
    assert by_title["B"]["push_forward_count"] == 0
    assert by_title["B"]["latest_status"] == "completed"
    assert len(by_title["B"]["spans"]) == 1
