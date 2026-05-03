"""测试 ProjectManager — 项目生命周期管理"""

import tempfile
from pathlib import Path

import pytest

from hagokyu.storage.project_manager import ProjectManager


@pytest.fixture
def pm(tmp_path):
    """默认 base_dir 的 ProjectManager"""
    return ProjectManager(tmp_path / "projects")


@pytest.fixture
def custom_pm(tmp_path):
    """可指定自定义目录的 ProjectManager"""
    return ProjectManager(tmp_path)


class TestProjectCRUD:
    def test_create_and_list(self, pm):
        p1 = pm.create("销售分析", "Q1渠道ROI")
        p2 = pm.create("用户研究")

        assert p1.name == "销售分析"
        assert p1.description == "Q1渠道ROI"
        assert p2.description == ""

        projects = pm.list()
        assert len(projects) == 2
        names = [p.name for p in projects]
        assert "销售分析" in names
        assert "用户研究" in names

    def test_create_duplicate_raises(self, pm):
        pm.create("测试项目")
        with pytest.raises(FileExistsError):
            pm.create("测试项目")

    def test_info(self, pm):
        pm.create("A项目", "描述A")
        info = pm.info("A项目")
        assert info is not None
        assert info.name == "A项目"
        assert info.description == "描述A"
        assert info.project_dir.name == "A项目"

    def test_info_nonexistent(self, pm):
        assert pm.info("不存在") is None

    def test_delete(self, pm):
        pm.create("待删除")
        assert pm.exists("待删除")

        pm.delete("待删除")
        assert not pm.exists("待删除")

    def test_delete_nonexistent(self, pm):
        assert pm.delete("不存在") is False

    def test_exists(self, pm):
        pm.create("已有项目")
        assert pm.exists("已有项目") is True
        assert pm.exists("不存在") is False

    def test_update_description(self, pm):
        pm.create("项目", "旧描述")
        assert pm.info("项目").description == "旧描述"

        pm.update_description("项目", "新描述")
        assert pm.info("项目").description == "新描述"

    def test_update_description_nonexistent(self, pm):
        assert pm.update_description("不存在", "描述") is False


class TestCustomDirectory:
    """测试自定义目录项目（通过 registry 支持）"""

    def test_create_in_custom_dir(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        p = custom_pm.create("自定义项目", parent_dir=custom_dir)
        assert p.project_dir.parent == custom_dir
        assert p.project_dir.name == "自定义项目"

    def test_list_finds_custom_dir_project(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        custom_pm.create("自定义项目", parent_dir=custom_dir)

        # list() 应该能找到注册表中的自定义目录项目
        projects = custom_pm.list()
        assert any(p.name == "自定义项目" for p in projects)

    def test_info_finds_custom_dir_project(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        custom_pm.create("自定义项目", parent_dir=custom_dir)

        info = custom_pm.info("自定义项目")
        assert info is not None
        assert info.name == "自定义项目"

    def test_exists_finds_custom_dir_project(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        custom_pm.create("自定义项目", parent_dir=custom_dir)

        assert custom_pm.exists("自定义项目") is True

    def test_get_project_dir_custom_dir(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        custom_pm.create("自定义项目", parent_dir=custom_dir)

        d = custom_pm.get_project_dir("自定义项目")
        assert d is not None
        assert d.name == "自定义项目"

    def test_delete_custom_dir_project(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        custom_pm.create("自定义项目", parent_dir=custom_dir)

        custom_pm.delete("自定义项目")
        assert not custom_pm.exists("自定义项目")

    def test_rename_updates_registry(self, custom_pm, tmp_path):
        custom_dir = tmp_path / "my_custom_projects"
        custom_pm.create("旧名称", parent_dir=custom_dir)

        result = custom_pm.rename("旧名称", "新名称")
        assert result is True

        # 旧名称应该不存在
        assert not custom_pm.exists("旧名称")
        # 新名称应该存在
        assert custom_pm.exists("新名称")
        info = custom_pm.info("新名称")
        assert info is not None
        assert info.name == "新名称"


class TestDirectoryStructure:
    """测试目录结构包含 memory/"""

    def test_memory_dir_created(self, pm):
        pm.create("测试项目")
        info = pm.info("测试项目")
        memory_dir = info.project_dir / "memory"
        assert memory_dir.exists()
        assert memory_dir.is_dir()

    def test_all_subdirs_exist(self, pm):
        pm.create("测试项目")
        info = pm.info("测试项目")
        for subdir in ("input", "process", "output", "memory"):
            assert (info.project_dir / subdir).exists()


class TestDataFiles:
    def test_add_data(self, pm, tmp_path):
        pm.create("项目")
        # 创建测试文件
        test_file = tmp_path / "test.csv"
        test_file.write_text("a,b\n1,2\n")

        df_info = pm.add_data("项目", test_file)
        assert df_info.name == "test.csv"
        assert df_info.source == "input"

        # 文件应该在 input/ 中
        info = pm.info("项目")
        assert len(info.data_files) == 1
        assert (info.project_dir / "input" / "test.csv").exists()

    def test_add_data_unique_name(self, pm, tmp_path):
        pm.create("项目")
        f1 = tmp_path / "data.csv"
        f1.write_text("a\n1")
        f2 = tmp_path / "data.csv"
        f2.write_text("b\n2")

        pm.add_data("项目", f1)
        df_info = pm.add_data("项目", f2)

        assert df_info.name == "data_1.csv"
        info = pm.info("项目")
        assert len(info.data_files) == 2

    def test_remove_data(self, pm, tmp_path):
        pm.create("项目")
        test_file = tmp_path / "test.csv"
        test_file.write_text("a\n1")
        pm.add_data("项目", test_file)

        pm.remove_data("项目", "test.csv")
        info = pm.info("项目")
        assert len(info.data_files) == 0
        assert not (info.project_dir / "input" / "test.csv").exists()


class TestStorageStats:
    def test_empty_project(self, pm):
        pm.create("空项目")
        stats = pm.get_storage_stats("空项目")
        assert stats["total"]["count"] == 0
        assert stats["total"]["size_mb"] == 0.0

    def test_stats_with_files(self, pm, tmp_path):
        pm.create("项目")
        # 添加输入文件
        f1 = tmp_path / "a.csv"
        f1.write_text("a" * 1024)  # 1KB
        pm.add_data("项目", f1)

        # 添加过程文件
        pm.add_process_file("项目", "cleaned.parquet", content=b"x" * 2048)  # 2KB

        stats = pm.get_storage_stats("项目")
        assert stats["input"]["count"] == 1
        assert stats["process"]["count"] == 1
        assert stats["total"]["count"] >= 2
        assert stats["total"]["size_mb"] > 0


class TestMemoryNotes:
    def test_save_and_load_memory(self, pm):
        pm.create("项目")
        notes = "# 项目背景\n\n这是Q1销售分析项目。"
        path = pm.save_memory("项目", notes)
        assert path is not None
        assert path.exists()

        loaded = pm.load_memory("项目")
        assert loaded == notes

    def test_load_memory_empty(self, pm):
        pm.create("空项目")
        loaded = pm.load_memory("空项目")
        assert loaded == ""

    def test_load_memory_nonexistent(self, pm):
        loaded = pm.load_memory("不存在")
        assert loaded == ""

    def test_get_memory_dir(self, pm):
        pm.create("项目")
        d = pm.get_memory_dir("项目")
        assert d is not None
        assert d.name == "memory"
        assert str(d).endswith("memory")

    def test_get_memory_dir_nonexistent(self, pm):
        d = pm.get_memory_dir("不存在")
        assert d is None

    def test_memory_persists(self, pm):
        """验证记忆文件真的存在磁盘上"""
        pm.create("项目")
        notes = "重要发现：渠道A的ROI明显高于B"
        pm.save_memory("项目", notes)

        # 直接读文件验证
        info = pm.info("项目")
        notes_path = info.project_dir / "memory" / "notes.md"
        assert notes_path.exists()
        assert notes_path.read_text() == notes


class TestRename:
    def test_rename_in_base_dir(self, pm):
        pm.create("旧项目")
        result = pm.rename("旧项目", "新项目")
        assert result is True

        assert not pm.exists("旧项目")
        assert pm.exists("新项目")
        info = pm.info("新项目")
        assert info.name == "新项目"
        assert info.project_dir.name == "新项目"

    def test_rename_nonexistent(self, pm):
        assert pm.rename("不存在", "新名称") is False

    def test_rename_target_exists(self, pm):
        pm.create("A")
        pm.create("B")
        assert pm.rename("A", "B") is False
