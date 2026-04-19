"""API tests for /api/tasks/*."""

from __future__ import annotations


async def test_create_task(authed_client):
    resp = await authed_client.post("/api/tasks", json={"category": "personal", "title": "Hello"})
    assert resp.status_code == 201
    body = resp.json()["task"]
    assert body["title"] == "Hello"
    assert body["status"] == "open"
    assert body["display_id"] == 1
    assert body["push_forward_count"] == 0


async def test_validation_empty_title(authed_client):
    resp = await authed_client.post("/api/tasks", json={"category": "personal", "title": ""})
    assert resp.status_code == 422


async def test_patch_changes_status(authed_client):
    resp = await authed_client.post("/api/tasks", json={"category": "personal", "title": "X"})
    task_id = resp.json()["task"]["id"]
    upd = await authed_client.patch(f"/api/tasks/{task_id}", json={"status": "completed"})
    assert upd.status_code == 200
    assert upd.json()["task"]["status"] == "completed"
    assert upd.json()["task"]["completed_at"] is not None


async def test_delete_lineage(authed_client):
    resp = await authed_client.post("/api/tasks", json={"category": "personal", "title": "X"})
    task_id = resp.json()["task"]["id"]
    d = await authed_client.delete(f"/api/tasks/{task_id}")
    assert d.status_code == 204
    g = await authed_client.get(f"/api/tasks/{task_id}")
    assert g.status_code == 404


async def test_reorder_endpoint(authed_client):
    a = (
        await authed_client.post("/api/tasks", json={"category": "personal", "title": "A"})
    ).json()["task"]
    b = (
        await authed_client.post("/api/tasks", json={"category": "personal", "title": "B"})
    ).json()["task"]
    c = (
        await authed_client.post("/api/tasks", json={"category": "personal", "title": "C"})
    ).json()["task"]
    resp = await authed_client.post(f"/api/tasks/{c['id']}/reorder", json={"new_position": 0})
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()["tasks"]]
    assert titles == ["C", "A", "B"]


async def test_get_task_includes_lineage(authed_client):
    resp = await authed_client.post("/api/tasks", json={"category": "personal", "title": "X"})
    task_id = resp.json()["task"]["id"]
    g = await authed_client.get(f"/api/tasks/{task_id}")
    assert g.status_code == 200
    body = g.json()
    assert body["task"]["title"] == "X"
    assert body["push_forward_count"] == 0
    assert len(body["lineage"]) == 1


async def test_user_isolation_on_get(client, test_user, other_user):
    await client.post("/api/auth/login", json={"email": test_user.email, "password": "secret"})
    created = await client.post("/api/tasks", json={"category": "personal", "title": "Mine"})
    task_id = created.json()["task"]["id"]
    await client.post("/api/auth/logout")
    await client.post("/api/auth/login", json={"email": other_user.email, "password": "secret"})
    g = await client.get(f"/api/tasks/{task_id}")
    assert g.status_code == 404


async def test_user_isolation_on_patch(client, test_user, other_user):
    await client.post("/api/auth/login", json={"email": test_user.email, "password": "secret"})
    created = await client.post("/api/tasks", json={"category": "personal", "title": "Mine"})
    task_id = created.json()["task"]["id"]
    await client.post("/api/auth/logout")
    await client.post("/api/auth/login", json={"email": other_user.email, "password": "secret"})
    p = await client.patch(f"/api/tasks/{task_id}", json={"title": "Stolen"})
    assert p.status_code == 404
