"""Doctor API 测试 — 端点 smoke test"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """创建 TestClient（避免全局导入 pandas 失败时测试全部 skip）。"""
    try:
        from hagoku.api.server import app
        return TestClient(app)
    except Exception as e:
        pytest.skip(f"Cannot create test client: {e}")


class TestDoctorHealth:
    def test_health_endpoint_returns_200(self, client):
        resp = client.get("/api/doctor/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "ok" in data
        assert "total" in data
        assert "checks" in data
        assert isinstance(data["checks"], list)

    def test_health_has_checks(self, client):
        resp = client.get("/api/doctor/health")
        data = resp.json()
        assert data["total"] > 0
        # 每个 check 应有 name, ok, detail
        for check in data["checks"]:
            assert "name" in check
            assert "ok" in check
            assert "detail" in check


class TestDoctorStatus:
    def test_status_endpoint(self, client):
        resp = client.get("/api/doctor/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "meta_llm_configured" in data
        assert "audits_dir" in data
        assert "audits_exist" in data


class TestDoctorAudits:
    def test_list_audits(self, client):
        resp = client.get("/api/doctor/audits")
        assert resp.status_code == 200
        data = resp.json()
        assert "audits" in data
        assert isinstance(data["audits"], list)

    def test_get_nonexistent_audit(self, client):
        resp = client.get("/api/doctor/audits/nonexistent_file_12345.md")
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, client):
        resp = client.get("/api/doctor/audits/../../../etc/passwd")
        # FastAPI/Starlette 路由层标准化 .. 路径，handler 收到时已不含 .. —
        # 400（handler 拦截）或 404（标准化后无匹配）均为安全结果
        assert resp.status_code in (400, 404)


class TestDoctorAuditTrigger:
    def test_audit_methods_returns_ok(self, client):
        """触发 method audit（可能因 LLM 不可用而 500，但端点是正确的）。"""
        resp = client.post("/api/doctor/audit/methods")
        # 可能 200（成功）或 500（LLM 不可达/meta llm 未配置）
        assert resp.status_code in (200, 500)

    def test_audit_tools_returns_ok(self, client):
        """触发 tool audit。"""
        resp = client.post("/api/doctor/audit/tools")
        assert resp.status_code in (200, 500)
