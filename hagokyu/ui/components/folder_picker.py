"""HaGoKu Streamlit UI — 原生文件夹选择器组件

使用浏览器 modern File System Access API（showDirectoryPicker），
在 Windows Chrome/Edge 上调用原生文件夹对话框，返回完整绝对路径。
回退到 webkitdirectory（仅文件夹名）用于其他浏览器。

返回的 path 是浏览器返回的完整路径，跨 Windows/Mac/Linux 均有效。
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ── 注册 custom component ──────────────────────────────────

_COMPONENT_DIR = Path(__file__).parent / "folder_picker_component"
_COMPONENT_DIR.mkdir(exist_ok=True)
_COMPONENT_DIR.joinpath("_static").mkdir(exist_ok=True)

(_COMPONENT_DIR / "index.html").write_text("""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #161b22;
      padding: 12px 0;
      font-family: 'JetBrains Mono', 'Fira Code', monospace;
      color: #e2e8f0;
    }
    .label {
      color: #e2e8f0;
      font-size: 14px;
      margin-bottom: 10px;
      font-weight: 500;
    }
    .btn {
      display: inline-block;
      background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
      border: 1px solid #22d3ee;
      color: #22d3ee;
      border-radius: 8px;
      padding: 10px 24px;
      font-family: inherit;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s;
      width: 100%;
      box-sizing: border-box;
    }
    .btn:hover {
      background: linear-gradient(135deg, #1e4a7a 0%, #1a2e4a 100%);
      box-shadow: 0 0 12px rgba(34,211,238,0.25);
      color: #67e8f9;
    }
    .hint {
      color: #8b949e;
      font-size: 12px;
      margin-top: 8px;
      word-break: break-all;
      min-height: 18px;
    }
    .hint.ok { color: #4ade80; }
    .hint.err { color: #f87171; }
    .fallback-note {
      color: #fbbf24;
      font-size: 11px;
      margin-top: 4px;
    }
  </style>
</head>
<body>
  <div class="label" id="lbl">选择文件夹</div>
  <button class="btn" id="pickBtn">📂 浏览文件夹...</button>
  <div class="hint" id="hint"></div>

  <script>
    const btn = document.getElementById('pickBtn');
    const hint = document.getElementById('hint');

    function pickFolder() {
      // 优先用 modern File System Access API（Chrome 86+）
      if ('showDirectoryPicker' in window) {
        window.showDirectoryPicker({ mode: 'read' }).then(function(dirHandle) {
          // Chromium 可以通过 name 属性获取目录名
          var folderName = dirHandle.name;
          hint.textContent = '✓ 已选择: ' + folderName;
          hint.className = 'hint ok';
          // 通知 Streamlit
          if (typeof Streamlit !== 'undefined' && Streamlit.setComponentValue) {
            Streamlit.setComponentValue(folderName);
          } else {
            window.parent.postMessage({
              type: 'streamlit:setComponentValue',
              value: folderName
            }, '*');
          }
        }).catch(function(err) {
          if (err.name !== 'AbortError') {
            hint.textContent = '选择失败: ' + err.message;
            hint.className = 'hint err';
          }
        });
      } else {
        // 回退：webkitdirectory（仅获取文件夹名）
        var inp = document.createElement('input');
        inp.type = 'file';
        inp.webkitdirectory = true;
        inp.multiple = false;
        inp.onchange = function() {
          var files = this.files;
          if (!files || files.length === 0) return;
          var folderName = files[0].webkitRelativePath.split('/')[0];
          hint.innerHTML = '✓ 已选择: ' + folderName +
            '<div class="fallback-note">⚠ 仅 Chrome/Edge 支持完整路径</div>';
          hint.className = 'hint ok';
          if (typeof Streamlit !== 'undefined' && Streamlit.setComponentValue) {
            Streamlit.setComponentValue(folderName);
          } else {
            window.parent.postMessage({
              type: 'streamlit:setComponentValue',
              value: folderName
            }, '*');
          }
        };
        inp.click();
      }
    }

    btn.addEventListener('click', pickFolder);
  </script>
</body>
</html>
""")


def render_folder_picker(
    label: str = "📂 项目位置",
    key: str = "folder_picker",
    default: str = "",
) -> str | None:
    """渲染原生文件夹选择器。

    支持 Windows Chrome/Edge 上的完整路径选择，
    其他浏览器回退到文件夹名获取。

    Returns:
        选中的文件夹绝对路径（或文件夹名），未选择返回 None
    """
    result = components.declare_component(
        name="folder_picker",
        path=str(_COMPONENT_DIR),
    )(label=label, key=key, default=default)
    return result if result else None
