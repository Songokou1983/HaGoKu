"""API Server 集成测试"""


import pytest

from hagokyu.api.server import app


class TestHealthEndpoint:
    """测试健康检查端点"""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        """测试 /api/health 返回 ok 状态"""
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
        from hagokyu.api.server import main
        assert callable(main)
