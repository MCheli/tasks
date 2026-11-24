"""Unit tests for scripts/tasks-agent with the HTTP layer faked.

Run from the repo root: python3 -m unittest discover -s tests/scripts
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "tasks-agent"
_loader = importlib.machinery.SourceFileLoader("tasks_agent", str(SCRIPT))
_spec = importlib.util.spec_from_loader("tasks_agent", _loader)
ta = importlib.util.module_from_spec(_spec)
_loader.exec_module(ta)

UUID_A = "11111111-1111-1111-1111-111111111111"
UUID_P = "22222222-2222-2222-2222-222222222222"


def task(n=7, **kw):
    t = {
        "id": UUID_A,
        "persistent_task_id": UUID_P,
        "display_id": n,
        "title": "Fix the thing",
        "status": "open",
        "owner": "agent",
        "agent_status": "open",
        "source": "weekly-security-sweep",
        "link": "https://github.com/MCheli/tasks/pull/1",
        "notes": None,
        "updated_at": "2026-11-23T20:00:00Z",
    }
    t.update(kw)
    return t


class FakeClient:
    """Records calls; answers from a list of tasks."""

    def __init__(self, tasks=None):
        self.tasks = tasks or []
        self.calls = []

    def request(self, method, path, params=None, body=None):
        self.calls.append((method, path, params, body))
        if method == "GET" and path == "/api/tasks":
            rows = self.tasks
            q = (params or {}).get("q")
            if q:
                rows = [t for t in rows if q.lower() in (t["title"] + (t["link"] or "")).lower()]
            return {"tasks": rows}
        if method == "GET":
            return {"task": self.tasks[0], "lineage": [], "notes_log": []}
        if method == "POST" and path == "/api/tasks":
            return {"task": task(n=99, title=body["title"], link=body.get("link"))}
        if method == "POST":
            return {"note": {"body": body["body"]}, "task": self.tasks[0]}
        if method == "PATCH":
            return {"task": task(**{k: v for k, v in body.items() if k != "agent_status"})}
        raise AssertionError(method)


def run(argv, client):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ta.main(argv, client=client)
    return code, out.getvalue(), err.getvalue()


class ParseRefTests(unittest.TestCase):
    def test_hash_number(self):
        self.assertEqual(ta.parse_ref("#123"), ("number", "123"))

    def test_bare_number(self):
        self.assertEqual(ta.parse_ref(" 42 "), ("number", "42"))

    def test_uuid(self):
        self.assertEqual(ta.parse_ref(UUID_A.upper()), ("uuid", UUID_A))

    def test_garbage(self):
        with self.assertRaises(ta.CliError):
            ta.parse_ref("#12a")


class ResolveTests(unittest.TestCase):
    def test_by_number_queries_only_the_given_list(self):
        c = FakeClient([task(n=5), task(n=7, id="x")])
        self.assertEqual(ta.resolve(c, "personal", "#7")["id"], "x")
        _, path, params, _ = c.calls[0]
        self.assertEqual(path, "/api/tasks")
        self.assertEqual(params["category"], "personal")
        self.assertEqual(params["owner"], "all")
        self.assertEqual(params["include_done"], "true")

    def test_by_uuid_or_persistent_id(self):
        c = FakeClient([task()])
        self.assertEqual(ta.resolve(c, "personal", UUID_P)["display_id"], 7)
        self.assertEqual(ta.resolve(c, "personal", UUID_A)["display_id"], 7)

    def test_not_found(self):
        with self.assertRaises(ta.CliError):
            ta.resolve(FakeClient([task(n=1)]), "personal", "2")


class ParserTests(unittest.TestCase):
    def test_defaults(self):
        a = ta.build_parser().parse_args(["list"])
        self.assertEqual(a.list, "personal")
        self.assertFalse(a.all_owners)

    def test_create_requires_source(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ta.build_parser().parse_args(["create", "x"])

    def test_create_rejects_done_status(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ta.build_parser().parse_args(["create", "x", "--source", "s", "--status", "done"])


class CommandTests(unittest.TestCase):
    def test_list_line_format(self):
        code, out, _ = run(["list"], FakeClient([task()]))
        self.assertEqual(code, 0)
        self.assertEqual(
            out.strip(),
            "#7 [open] Fix the thing (weekly-security-sweep) https://github.com/MCheli/tasks/pull/1",
        )

    def test_list_params(self):
        c = FakeClient([])
        run(["list", "--status", "blocked", "-q", "cve", "--include-done"], c)
        params = c.calls[0][2]
        self.assertEqual(params["owner"], "agent")
        self.assertEqual(params["status"], "blocked")
        self.assertEqual(params["q"], "cve")

    def test_list_json(self):
        _, out, _ = run(["list", "--json"], FakeClient([task()]))
        self.assertEqual(json.loads(out)[0]["display_id"], 7)

    def test_create_body(self):
        c = FakeClient([])
        code, out, _ = run(["create", "New", "--source", "s", "--link", "L", "--notes", "N"], c)
        self.assertEqual(code, 0)
        method, path, _, body = c.calls[-1]
        self.assertEqual((method, path), ("POST", "/api/tasks"))
        self.assertEqual(
            body,
            {
                "category": "personal",
                "title": "New",
                "owner": "agent",
                "source": "s",
                "agent_status": "open",
                "link": "L",
                "notes": "N",
            },
        )
        self.assertTrue(out.startswith("#99 "))

    def test_create_if_missing_same_title(self):
        c = FakeClient([task(title="fix THE thing")])
        code, out, _ = run(["create", "Fix the thing", "--source", "s", "--if-missing"], c)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("exists: #7"))
        self.assertFalse([x for x in c.calls if x[0] == "POST"])

    def test_create_if_missing_same_link(self):
        c = FakeClient([task(title="Other", link="https://x/1")])
        code, out, _ = run(
            ["create", "New title", "--source", "s", "--link", "https://x/1", "--if-missing"], c
        )
        self.assertTrue(out.startswith("exists: #7"))

    def test_create_if_missing_creates_when_absent(self):
        c = FakeClient([task(title="Other", link="https://x/2")])
        run(["create", "New title", "--source", "s", "--link", "https://x/1", "--if-missing"], c)
        self.assertEqual(c.calls[-1][:2], ("POST", "/api/tasks"))

    def test_update_agent_status(self):
        c = FakeClient([task()])
        run(["update", "#7", "--status", "in_progress", "--title", "T"], c)
        self.assertEqual(
            c.calls[-1], ("PATCH", f"/api/tasks/{UUID_A}", None, {"agent_status": "in_progress", "title": "T"})
        )

    def test_update_human_item_maps_status(self):
        c = FakeClient([task(owner="human", agent_status=None)])
        run(["update", "7", "--status", "done"], c)
        self.assertEqual(c.calls[-1][3], {"status": "completed"})

    def test_update_needs_a_field(self):
        code, _, err = run(["update", "7"], FakeClient([task()]))
        self.assertEqual(code, 1)
        self.assertIn("nothing to update", err)

    def test_note(self):
        c = FakeClient([task()])
        run(["note", "#7", "hello", "--author", "me"], c)
        self.assertEqual(
            c.calls[-1], ("POST", f"/api/tasks/{UUID_A}/notes", None, {"body": "hello", "author": "me"})
        )

    def test_done_with_note(self):
        c = FakeClient([task()])
        run(["done", "7", "--note", "fixed"], c)
        self.assertEqual(c.calls[-2][1], f"/api/tasks/{UUID_A}/notes")
        self.assertEqual(c.calls[-1], ("PATCH", f"/api/tasks/{UUID_A}", None, {"agent_status": "done"}))

    def test_unknown_ref_exits_nonzero(self):
        code, out, err = run(["get", "#404"], FakeClient([task()]))
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(), "tasks-agent: task #404 not found in the personal list")


class ClientTests(unittest.TestCase):
    def test_401_says_auth_failed_only(self):
        import urllib.error
        from unittest import mock

        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        c = ta.Client("https://example.invalid", key_fn=lambda: "secret-value")
        with mock.patch.object(ta.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(ta.CliError) as cm:
                c.request("GET", "/api/tasks")
        self.assertEqual(str(cm.exception), "auth failed")

    def test_env_key_skips_agent_op(self):
        from unittest import mock

        with mock.patch.dict(ta.os.environ, {"TASKS_API_KEY": "k"}), mock.patch.object(
            ta.subprocess, "run"
        ) as r:
            self.assertEqual(ta.api_key(), "k")
            r.assert_not_called()


if __name__ == "__main__":
    unittest.main()
