"""API Server 集成测试"""

from hagoku.api.server import app


class TestHealthEndpoint:
    """测试健康检查端点"""

    def test_health_returns_ok(self):
        """测试 /api/health 返回 ok 状态（同步 TestClient，避免依赖 pytest-asyncio）"""
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "version" in response.json()


class TestServerMain:
    """测试 server 启动逻辑"""

    def test_main_imports_without_error(self):
        """测试 main 函数可以正常导入"""
        from hagoku.api.server import main
        assert callable(main)


class TestProjectRunsGuardrailsContract:
    """runs 列表 API：护栏拦截行的 status 与 guardrails_notice_url（契约）"""

    def test_runs_guardrails_blocked_has_notice_url_not_completed(self, tmp_path, monkeypatch):
        import json

        proj = tmp_path / "projects" / "demo"
        run_dir = proj / "runs" / "20260514_120000"
        out = run_dir / "output"
        out.mkdir(parents=True)
        notice = out / "GUARDRAILS_BLOCKED.md"
        notice.write_text("# 护栏\n", encoding="utf-8")
        meta = {
            "run_id": "20260514_120000",
            "query": "test query",
            "output_path": str(notice),
            "guardrails_blocked": True,
        }
        (run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")

        monkeypatch.setattr("hagoku.api.server._projects_root", lambda: tmp_path / "projects")

        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/projects/demo/runs")
        assert r.status_code == 200
        body = r.json()
        assert len(body["runs"]) == 1
        row = body["runs"][0]
        assert row["status"] == "guardrails_blocked"
        assert row["guardrails_blocked"] is True
        assert row["report_url"] is None
        assert row["guardrails_notice_url"] == (
            "/api/reports/demo/20260514_120000/GUARDRAILS_BLOCKED.md"
        )

    def test_detail_last_status_guardrails_when_only_blocked_md(self, tmp_path, monkeypatch):
        import json

        proj = tmp_path / "projects" / "demo"
        run_dir = proj / "runs" / "20260514_120000"
        out = run_dir / "output"
        out.mkdir(parents=True)
        notice = out / "GUARDRAILS_BLOCKED.md"
        notice.write_text("# 护栏\n", encoding="utf-8")
        meta = {
            "run_id": "20260514_120000",
            "query": "q",
            "output_path": str(notice),
        }
        (run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")

        monkeypatch.setattr("hagoku.api.server._projects_root", lambda: tmp_path / "projects")

        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/projects/demo/detail")
        assert r.status_code == 200
        d = r.json()
        assert d["last_status"] == "guardrails_blocked"
        assert d["last_guardrails_blocked"] is True


class TestKanbanTasksEndpoint:
    """GET /api/projects/{name}/kanban/tasks — Scribe 看板只读"""

    def test_kanban_tasks_empty_when_no_db(self, tmp_path, monkeypatch):
        proj = tmp_path / "projects" / "nop"
        proj.mkdir(parents=True)
        monkeypatch.setattr("hagoku.api.server._projects_root", lambda: tmp_path / "projects")
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/projects/nop/kanban/tasks")
        assert r.status_code == 200
        assert r.json()["tasks"] == []

    def test_kanban_tasks_returns_rows_ordered(self, tmp_path, monkeypatch):
        from hagoku.storage.kanban import KanbanDB

        proj = tmp_path / "projects" / "k1"
        proj.mkdir(parents=True)
        monkeypatch.setattr("hagoku.api.server._projects_root", lambda: tmp_path / "projects")
        kb = KanbanDB.get_instance(proj)
        kb.create_task("scout", "Scout: A", "d1")
        kb.create_task("cleaner", "Cleaner: B", "d2")

        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/projects/k1/kanban/tasks")
        assert r.status_code == 200
        tasks = r.json()["tasks"]
        assert len(tasks) == 2
        assert tasks[0]["agent"] == "scout"
        assert tasks[0]["description"] == "d1"
        assert tasks[1]["title"] == "Cleaner: B"

    def test_kanban_tasks_404_missing_project(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hagoku.api.server._projects_root", lambda: tmp_path / "projects")
        (tmp_path / "projects").mkdir(parents=True)
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/projects/ghost/kanban/tasks")
        assert r.status_code == 404
