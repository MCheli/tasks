"""The agent list: owner dimension, agent fields, notes log, filters, auto-forward."""

from __future__ import annotations


async def _create(client, **fields) -> dict:
    payload = {"category": "personal", "title": "x", **fields}
    r = await client.post("/api/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["task"]


async def test_default_owner_is_human(authed_client):
    """The Chore tracker posts {category, title} and must keep getting a human task."""
    t = await _create(authed_client, title="Chores")
    assert t["owner"] == "human"
    assert t["agent_status"] is None
    assert t["source"] is None and t["link"] is None
    assert t["note_count"] == 0


async def test_create_agent_task_defaults(authed_client):
    t = await _create(
        authed_client,
        title="Fix CVE",
        owner="agent",
        source="weekly-security-sweep",
        link="https://github.com/MCheli/tasks/pull/1",
    )
    assert t["owner"] == "agent"
    assert t["agent_status"] == "open"
    assert t["status"] == "open"
    assert t["source"] == "weekly-security-sweep"
    assert t["link"].endswith("/pull/1")


async def test_current_cycle_hides_agent_items_by_default(authed_client):
    await _create(authed_client, title="Mine")
    await _create(authed_client, title="Theirs", owner="agent")

    default = (
        await authed_client.get("/api/cycles/current", params={"category": "personal"})
    ).json()
    assert [t["title"] for t in default["tasks"]["open"]] == ["Mine"]
    assert default["summary"]["open"] == 1

    agents = (
        await authed_client.get(
            "/api/cycles/current", params={"category": "personal", "owner": "agent"}
        )
    ).json()
    assert [t["title"] for t in agents["tasks"]["open"]] == ["Theirs"]

    everything = (
        await authed_client.get(
            "/api/cycles/current", params={"category": "personal", "owner": "all"}
        )
    ).json()
    assert sorted(t["title"] for t in everything["tasks"]["open"]) == ["Mine", "Theirs"]
    assert everything["summary"]["open"] == 2


async def test_agent_status_and_completion_stay_in_step(authed_client):
    t = await _create(authed_client, owner="agent")

    r = await authed_client.patch(f"/api/tasks/{t['id']}", json={"agent_status": "in_progress"})
    assert r.json()["task"]["agent_status"] == "in_progress"
    assert r.json()["task"]["status"] == "open"

    r = await authed_client.patch(f"/api/tasks/{t['id']}", json={"agent_status": "done"})
    body = r.json()["task"]
    assert body["status"] == "completed" and body["completed_at"] is not None
    assert body["agent_status"] == "done"

    # Reopening through the app's status puts the agent status back to open.
    r = await authed_client.patch(f"/api/tasks/{t['id']}", json={"status": "open"})
    assert r.json()["task"]["agent_status"] == "open"
    assert r.json()["task"]["completed_at"] is None

    # Completing through the app's status marks it done.
    r = await authed_client.patch(f"/api/tasks/{t['id']}", json={"status": "completed"})
    assert r.json()["task"]["agent_status"] == "done"

    # A blocked status on a done item reopens it.
    r = await authed_client.patch(f"/api/tasks/{t['id']}", json={"agent_status": "blocked"})
    assert r.json()["task"]["status"] == "open"
    assert r.json()["task"]["agent_status"] == "blocked"


async def test_agent_status_is_ignored_for_human_items(authed_client):
    t = await _create(authed_client)
    r = await authed_client.patch(f"/api/tasks/{t['id']}", json={"agent_status": "blocked"})
    assert r.status_code == 200
    assert r.json()["task"]["agent_status"] is None
    assert r.json()["task"]["status"] == "open"


async def test_flat_list_filters(authed_client):
    await _create(authed_client, title="Human open")
    a = await _create(authed_client, title="Agent blocked", owner="agent", source="sweep")
    await authed_client.patch(f"/api/tasks/{a['id']}", json={"agent_status": "blocked"})
    b = await _create(authed_client, title="Agent done", owner="agent", source="thread-7")
    await authed_client.patch(f"/api/tasks/{b['id']}", json={"agent_status": "done"})
    await _create(authed_client, title="Work agent", owner="agent", category="professional")

    everything = (await authed_client.get("/api/tasks")).json()["tasks"]
    assert sorted(t["title"] for t in everything) == ["Agent blocked", "Human open", "Work agent"]

    personal_agents = (
        await authed_client.get("/api/tasks", params={"category": "personal", "owner": "agent"})
    ).json()["tasks"]
    assert [t["title"] for t in personal_agents] == ["Agent blocked"]

    blocked = (await authed_client.get("/api/tasks", params={"status": "blocked"})).json()["tasks"]
    assert [t["title"] for t in blocked] == ["Agent blocked"]

    done = (await authed_client.get("/api/tasks", params={"status": "done"})).json()["tasks"]
    assert [t["title"] for t in done] == ["Agent done"]

    with_done = (
        await authed_client.get("/api/tasks", params={"owner": "agent", "include_done": "true"})
    ).json()["tasks"]
    assert len(with_done) == 3

    by_source = (
        await authed_client.get("/api/tasks", params={"q": "thread-7", "include_done": 1})
    ).json()
    assert [t["title"] for t in by_source["tasks"]] == ["Agent done"]

    humans = (await authed_client.get("/api/tasks", params={"owner": "human"})).json()["tasks"]
    assert [t["title"] for t in humans] == ["Human open"]


async def test_overview_has_all_four_lists(authed_client):
    await _create(authed_client, title="P-human")
    await _create(authed_client, title="P-agent", owner="agent")
    done = await _create(authed_client, title="P-agent-done", owner="agent")
    await authed_client.patch(f"/api/tasks/{done['id']}", json={"agent_status": "done"})
    await _create(authed_client, title="W-human", category="professional")

    r = await authed_client.get("/api/tasks/overview")
    assert r.status_code == 200
    body = r.json()
    assert [t["title"] for t in body["personal"]["human"]["open"]] == ["P-human"]
    assert [t["title"] for t in body["personal"]["agent"]["open"]] == ["P-agent"]
    assert body["personal"]["agent"]["counts"] == {
        "open": 1,
        "completed": 1,
        "canceled": 0,
        "in_progress": 0,
        "blocked": 0,
    }
    assert [t["title"] for t in body["professional"]["human"]["open"]] == ["W-human"]
    assert body["professional"]["agent"]["open"] == []
    assert body["professional"]["agent"]["counts"]["open"] == 0
    assert body["personal"]["cycle_id"] is not None


async def test_notes_log(authed_client, test_user):
    t = await _create(authed_client, owner="agent", source="sweep")
    r = await authed_client.post(f"/api/tasks/{t['id']}/notes", json={"body": "Opened PR #12"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["note"]["body"] == "Opened PR #12"
    assert body["note"]["author"] == test_user.email  # signed-in caller, no author given
    assert body["task"]["note_count"] == 1

    r = await authed_client.post(
        f"/api/tasks/{t['id']}/notes", json={"body": "Merged", "author": "security-sweep"}
    )
    assert r.json()["note"]["author"] == "security-sweep"

    detail = (await authed_client.get(f"/api/tasks/{t['id']}")).json()
    assert [n["body"] for n in detail["notes_log"]] == ["Opened PR #12", "Merged"]
    assert detail["task"]["note_count"] == 2

    empty = await authed_client.post(f"/api/tasks/{t['id']}/notes", json={"body": ""})
    assert empty.status_code == 422


async def test_note_author_defaults_to_api_key_name(client, authed_client):
    key = (await authed_client.post("/api/api-keys", json={"name": "chore-tracker"})).json()["key"]
    t = await _create(authed_client, owner="agent")
    await client.post("/api/auth/logout")
    r = await client.post(
        f"/api/tasks/{t['id']}/notes", json={"body": "hi"}, headers={"X-API-Key": key}
    )
    assert r.status_code == 201, r.text
    assert r.json()["note"]["author"] == "chore-tracker"


async def test_transition_carries_agent_items_without_an_action(authed_client):
    human = await _create(authed_client, title="Mine")
    agent = await _create(authed_client, title="Theirs", owner="agent", source="sweep", link="u")
    await authed_client.patch(f"/api/tasks/{agent['id']}", json={"agent_status": "in_progress"})
    await authed_client.post(f"/api/tasks/{agent['id']}/notes", json={"body": "progress"})
    cycle = (
        await authed_client.get("/api/cycles/current", params={"category": "personal"})
    ).json()["cycle"]

    # Only the human item is in the actions, as the transition screen sends it.
    r = await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={
            "actions": [{"persistent_task_id": human["persistent_task_id"], "action": "complete"}]
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["summary"] == {"forwarded": 1, "completed": 1, "canceled": 0}
    assert r.json()["new_cycle_tasks"]["open"] == []  # the response lists Mark's items

    agents = (
        await authed_client.get(
            "/api/cycles/current", params={"category": "personal", "owner": "agent"}
        )
    ).json()["tasks"]["open"]
    assert len(agents) == 1
    carried = agents[0]
    assert carried["persistent_task_id"] == agent["persistent_task_id"]
    assert carried["push_forward_count"] == 1
    assert carried["agent_status"] == "in_progress"
    assert carried["source"] == "sweep" and carried["link"] == "u"
    assert carried["note_count"] == 1  # the log follows the lineage


async def test_transition_still_requires_actions_for_human_items(authed_client):
    await _create(authed_client, title="Mine")
    await _create(authed_client, title="Theirs", owner="agent")
    cycle = (
        await authed_client.get("/api/cycles/current", params={"category": "personal"})
    ).json()["cycle"]
    r = await authed_client.post(f"/api/cycles/{cycle['id']}/transition", json={"actions": []})
    assert r.status_code == 400


async def test_transition_honors_an_action_given_for_an_agent_item(authed_client):
    agent = await _create(authed_client, title="Theirs", owner="agent")
    cycle = (
        await authed_client.get("/api/cycles/current", params={"category": "personal"})
    ).json()["cycle"]
    r = await authed_client.post(
        f"/api/cycles/{cycle['id']}/transition",
        json={
            "actions": [{"persistent_task_id": agent["persistent_task_id"], "action": "complete"}]
        },
    )
    assert r.status_code == 201
    assert r.json()["summary"]["completed"] == 1
    old = (await authed_client.get(f"/api/cycles/{cycle['id']}", params={"owner": "agent"})).json()
    assert old["tasks"]["completed"][0]["agent_status"] == "done"


async def test_positions_are_independent_per_owner(authed_client):
    h1 = await _create(authed_client, title="H1")
    a1 = await _create(authed_client, title="A1", owner="agent")
    h2 = await _create(authed_client, title="H2")
    a2 = await _create(authed_client, title="A2", owner="agent")
    assert (h1["position"], h2["position"]) == (0, 1)
    assert (a1["position"], a2["position"]) == (0, 1)

    r = await authed_client.post(f"/api/tasks/{a2['id']}/reorder", json={"new_position": 0})
    assert [t["title"] for t in r.json()["tasks"]] == ["A2", "A1"]
    humans = (
        await authed_client.get("/api/cycles/current", params={"category": "personal"})
    ).json()
    assert [t["title"] for t in humans["tasks"]["open"]] == ["H1", "H2"]


async def test_history_is_human_only_by_default(authed_client):
    await _create(authed_client, title="Mine")
    await _create(authed_client, title="Theirs", owner="agent")
    h = (await authed_client.get("/api/history", params={"category": "personal"})).json()
    assert [lin["title"] for lin in h["lineages"]] == ["Mine"]
    h = (
        await authed_client.get("/api/history", params={"category": "personal", "owner": "agent"})
    ).json()
    assert [lin["title"] for lin in h["lineages"]] == ["Theirs"]


async def test_list_cycles_counts_follow_owner(authed_client):
    await _create(authed_client, title="Mine")
    await _create(authed_client, title="Theirs", owner="agent")
    r = (await authed_client.get("/api/cycles", params={"category": "personal"})).json()
    assert r["cycles"][0]["task_counts"]["open"] == 1
    r = (
        await authed_client.get("/api/cycles", params={"category": "personal", "owner": "all"})
    ).json()
    assert r["cycles"][0]["task_counts"]["open"] == 2
