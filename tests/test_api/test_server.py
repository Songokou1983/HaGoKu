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



class TestConfigEndpoints:
    """GET /api/config、POST /api/config/llm"""

    def test_get_config_has_llm(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/config")
        assert r.status_code == 200
        body = r.json()
        assert "llm" in body
        assert "base_url" in body["llm"]
        assert "model" in body["llm"]
        assert "api_key_configured" in body["llm"]
        assert isinstance(body["llm"]["api_key_configured"], bool)

    def test_post_llm_writes_env_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr("hagoku.api.server._hagoku_dotenv_path", lambda: env_file)

        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.post(
            "/api/config/llm",
            json={
                "base_url": "http://llm.test:9999/v1",
                "model": "test-model-x",
                "api_key": "sk-test-secret",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["llm"]["base_url"] == "http://llm.test:9999/v1"
        assert data["llm"]["model"] == "test-model-x"
        assert data["llm"]["model"] == "test-model-x"
        
        assert data["llm"]["api_key_configured"] is True
        text = env_file.read_text(encoding="utf-8")
        assert "HAGOKU_LLM_BASE_URL" in text
        assert "http://llm.test:9999/v1" in text
        assert "HAGOKU_LLM_MODEL" in text
        assert "test-model-x" in text
        assert "HAGOKU_LLM_API_KEY" in text
        from dotenv import dotenv_values


    def test_post_llm_writes_model(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr("hagoku.api.server._hagoku_dotenv_path", lambda: env_file)

        from dotenv import dotenv_values
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.post(
            "/api/config/llm",
            json={
                "base_url": "http://llm.test/v1",
                "model": "big-model",
                "api_key": "",
                "sub_model": "big-model",
            },
        )
        assert r.status_code == 200
        data = r.json()

    def test_post_llm_400_when_missing_model(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        monkeypatch.setattr("hagoku.api.server._hagoku_dotenv_path", lambda: env_file)
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.post(
            "/api/config/llm",
            json={
                "base_url": "http://x/v1",
                "model": "   ",
                "api_key": "",
            },
        )
        assert r.status_code == 400

    def test_projects_root_respects_hagokyu_project_dir(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom_projects"
        custom.mkdir()
        monkeypatch.setenv("HAGOKU_PROJECT_DIR", str(custom))
        from hagoku.api.server import _projects_root

        assert _projects_root().resolve() == custom.resolve()


class TestKbContent:
    """GET /api/kb/content — 知识库 Markdown 正文"""

    def test_kb_content_returns_html(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/kb/content", params={"filename": "statistics/ttest.md"})
        assert r.status_code == 200
        data = r.json()
        assert data["filename"] == "statistics/ttest.md"
        assert data.get("title")
        assert "<" in data.get("html", "")

    def test_kb_content_rejects_traversal(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/kb/content", params={"filename": "../pyproject.toml"})
        assert r.status_code in (400, 404)

    def test_kb_content_unknown_file(self):
        from fastapi.testclient import TestClient

        client = TestClient(app)
        r = client.get("/api/kb/content", params={"filename": "statistics/nope.md"})
        assert r.status_code == 404
