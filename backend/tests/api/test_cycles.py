"""API tests for /api/cycles/*."""
from __future__ import annotations

import pytest


async def test_get_current_creates_cycle(authed_client):
    resp = await authed_client.get("/api/cycles/current", params={"category": "personal"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cycle"]["category"] == "personal"
    assert body["cycle"]["ended_at"] is None
    assert body["summary"] == {"open": 0, "completed": 0, "canceled": 0}


async def test_get_current_requires_valid_category(authed_client):
    resp = await authed_client.get("/api/cycles/current", params={"category": "weird"})
    assert resp.status_code == 422


async def test_list_cycles_empty(authed_client):
    resp = await authed_client.get("/api/cycles", params={"category": "personal"})
    assert resp.status_code == 200
    assert resp.json() == {"cycles": [], "total": 0}


async def test_get_other_users_cycle_404(client, test_user, other_user):
    # Log in as test_user and create their cycle.
    await client.post(
        "/api/auth/login", json={"email": test_user.email, "password": "secret"}
    )
    resp = await client.get("/api/cycles/current", params={"category": "personal"})
    cycle_id = resp.json()["cycle"]["id"]

    # Switch users.
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login", json={"email": other_user.email, "password": "secret"}
    )
    resp = await client.get(f"/api/cycles/{cycle_id}")
    assert resp.status_code == 404


async def test_unauth_get_current_rejected(client):
    resp = await client.get("/api/cycles/current", params={"category": "personal"})
    assert resp.status_code == 401
