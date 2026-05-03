"""HaGoKu 桌面启动器 — 双击即可运行，无需终端"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── 入口检测 ────────────────────────────────────────────────
# PyInstaller 打包时会设置 sys.frozen + _MEIPASS
_IS_FROZEN = getattr(sys, "frozen", False)
_MEI_PASS = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent))


def _get_python_cmd() -> list[str]:
    """获取 Python 解释器路径（优先用 venv）"""
    venv_python = Path(sys.prefix) / "bin" / "python"
    if venv_python.exists():
        return [str(venv_python)]
    return [sys.executable]


def _streamlit_script() -> str:
    """Streamlit 入口脚本路径"""
    if _IS_FROZEN:
        return os.path.join(_MEI_PASS, "hagokyu", "ui", "__main__.py")
    # 开发模式：从包内找（__file__ 为 None 时用 __path__）
    import hagokyu.ui
    if getattr(hagokyu.ui, "__file__", None):
        ui_dir = Path(hagokyu.ui.__file__).parent
    else:
        ui_dir = Path(next(iter(hagokyu.ui.__path__)))
    return str(ui_dir / "__main__.py")


def _start_streamlit():
    """后台启动 Streamlit 服务器"""
    import subprocess

    script = _streamlit_script()
    cmd = _get_python_cmd() + [
        "-m", "streamlit", "run",
        "--server.headless", "true",
        "--server.port", "8501",
        script,
    ]

    # 设置环境，让子进程知道不要二次启动 subprocess
    env = dict(os.environ)
    env["HAGOKYU_SUBPROCESS"] = "1"

    # 切换到正确工作目录
    if _IS_FROZEN:
        work_dir = _MEI_PASS
    else:
        work_dir = str(Path(__file__).resolve().parent.parent.parent)

    subprocess.Popen(
        cmd,
        cwd=work_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_server(timeout: float = 10) -> bool:
    """等待服务器就绪"""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen("http://localhost:8501", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _open_browser():
    """等待服务器就绪后打开浏览器"""
    time.sleep(2)  # 简短等待
    if _wait_for_server(timeout=15):
        webbrowser.open("http://localhost:8501")
    else:
        # 服务器启动失败，尝试直接打开（Streamlit 可能已就绪）
        webbrowser.open("http://localhost:8501")


def _show_window():
    """显示原生桌面窗口"""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        # 无 tkinter（极少情况），静默跳过
        return

    root = tk.Tk()
    root.title("HaGoKu — 数据分析平台")
    root.geometry("420x180")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    # 居中
    root.update_idletasks()
    w = root.winfo_screenwidth()
    h = root.winfo_screenheight()
    x = (w - 420) // 2
    y = (h - 180) // 2
    root.geometry(f"420x180+{x}+{y}")

    # 图标（如果有）
    try:
        root.iconname("HaGoKu")
    except Exception:
        pass

    # 内容
    frame = tk.Frame(root, bg="#0a0e17")
    frame.pack(fill="both", expand=True)

    title = tk.Label(
        frame, text="HaGoKu",
        font=("Inter", 22, "bold"),
        fg="#a78bfa", bg="#0a0e17",
    )
    title.pack(pady=(20, 4))

    subtitle = tk.Label(
        frame, text="数据分析平台 · 启动中...",
        font=("Inter", 11),
        fg="#8b949e", bg="#0a0e17",
    )
    subtitle.pack(pady=(0, 16))

    btn = tk.Button(
        frame, text="打开 HaGoKu",
        font=("Inter", 11, "bold"),
        fg="#f0fdfa", bg="#0e7490",
        activeforeground="#f0fdfa", activebackground="#0891b2",
        relief="flat", cursor="hand2",
        command=lambda: webbrowser.open("http://localhost:8501"),
    )
    btn.configure(width=20)
    btn.pack(pady=(0, 12))

    hint = tk.Label(
        frame, text="或浏览器直接访问 http://localhost:8501",
        font=("Inter", 9),
        fg="#4b5563", bg="#0a0e17",
    )
    hint.pack()

    # 服务器就绪后更新文字
    def _check():
        if _wait_for_server(timeout=3):
            title.config(text="✅ HaGoKu 已就绪")
            subtitle.config(text="数据分析平台 · 浏览器已自动打开")
        else:
            title.config(text="⚠️ 启动中，请稍候...")
            root.after(2000, _check)

    root.after(1000, _check)

    # 关闭窗口时只隐藏，不退出进程
    def _on_close():
        root.withdraw()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()


def run():
    """启动桌面应用"""
    # 后台启动 Streamlit
    t = threading.Thread(target=_start_streamlit, daemon=True)
    t.start()

    # 后台尝试打开浏览器
    browser_t = threading.Thread(target=_open_browser, daemon=True)
    browser_t.start()

    # 显示原生窗口
    _show_window()


if __name__ == "__main__":
    run()
