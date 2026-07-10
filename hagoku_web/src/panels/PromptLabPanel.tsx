import { useState, useEffect, useCallback } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { ActionButton } from "../components/ActionButton";
import { StatusBanner } from "../components/StatusBanner";
import {
  Play,
  GitCompare,
  Save,
  Plus,
  Trash2,
  Pencil,
  ChevronDown,
  ChevronRight,
  Sparkles,
  CheckCircle2,
  FlaskConical,
  Eye,
  EyeOff,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────

interface PresetInfo {
  id: string;
  name: string;
  icon: string;
  description: string;
  active: boolean;
}

interface LabResult {
  content: string;
  tool_calls: Array<{ name: string; arguments: string }>;
  model?: string;
}

interface CompareResult {
  ok: boolean;
  baseline: LabResult;
  current: LabResult;
  diff: { changed_paths: string[]; similarity: number };
}

const ICON_MAP: Record<string, string> = {
  "bar-chart": "📊",
  "trending-up": "📈",
  "shopping-cart": "🛒",
};

// ── Component ──────────────────────────────────────────────────────

export default function PromptLabPanel() {
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ── 每个预设的展开状态 ──
  const [expandedPresets, setExpandedPresets] = useState<Set<string>>(new Set());

  // ── 新建/编辑弹窗 ──
  const [editingPreset, setEditingPreset] = useState<PresetInfo | null>(null);
  const [editName, setEditName] = useState("");
  const [editIcon, setEditIcon] = useState("bar-chart");
  const [editDesc, setEditDesc] = useState("");
  const [editPrompt, setEditPrompt] = useState("");

  // ── 模拟实验室 ──
  const [showLab, setShowLab] = useState(false);
  const [labBase, setLabBase] = useState("general"); // 基于哪个预设
  const [labPrompt, setLabPrompt] = useState("");
  const [labMessage, setLabMessage] = useState("");
  const [labRunning, setLabRunning] = useState(false);
  const [labResult, setLabResult] = useState<LabResult | null>(null);
  const [labCompare, setLabCompare] = useState<CompareResult | null>(null);

  // ── Load ──────────────────────────────────────────────────────

  const loadPresets = useCallback(async () => {
    try {
      const r = await fetch("/api/prompt-lab/presets");
      const d = await r.json();
      setPresets(d.presets || []);
    } catch {}
  }, []);

  useEffect(() => { loadPresets(); }, [loadPresets]);

  // ── 激活 ──────────────────────────────────────────────────────

  const handleActivate = async (id: string) => {
    setLoading(true);
    try {
      await fetch("/api/prompt-lab/presets/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      await loadPresets();
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  };

  const handleDeactivate = async () => {
    setLoading(true);
    try {
      await fetch("/api/prompt-lab/presets/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: "" }),
      });
      await loadPresets();
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  };

  // ── 展开/折叠源码 ──

  const toggleExpand = (id: string) => {
    setExpandedPresets((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ── 加载预设内容到编辑器 ──

  const loadPresetContent = async (id: string) => {
    try {
      const r = await fetch(`/api/prompt-lab/presets/${id}/content`);
      const d = await r.json();
      if (d.ok) return d.content;
    } catch {}
    return "";
  };

  // ── 编辑预设（打开弹窗） ──

  const handleStartEdit = async (preset: PresetInfo) => {
    const content = await loadPresetContent(preset.id);
    setEditingPreset(preset);
    setEditName(preset.name);
    setEditIcon(preset.icon);
    setEditDesc(preset.description);
    setEditPrompt(content);
  };

  const handleSaveEdit = async () => {
    if (!editName.trim()) return;
    setLoading(true);
    setError("");
    try {
      if (editingPreset && editingPreset.id && editingPreset.id !== "general") {
        // 编辑已有预设 → PUT 更新
        const resp = await fetch(`/api/prompt-lab/presets/${editingPreset.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: editName.trim(), icon: editIcon, description: editDesc.trim(), prompt: editPrompt }),
        });
        const data = await resp.json();
        if (!data.ok) { setError(data.detail || "保存失败"); return; }
      } else {
        // 编辑默认预设或新建 → 创建新预设
        const resp = await fetch("/api/prompt-lab/presets/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: editName.trim(), icon: editIcon, description: editDesc.trim(), prompt: editPrompt }),
        });
        const data = await resp.json();
        if (!data.ok) { setError(data.detail || "创建失败"); return; }
      }
      await loadPresets();
      setEditingPreset(null);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  };

  // ── 删除预设 ──

  const handleDelete = async (preset: PresetInfo) => {
    if (preset.id === "general") return;
    if (!confirm(`确定删除「${preset.name}」？此操作不可撤销。`)) return;
    setLoading(true);
    try {
      // 通过 API 删除：先反激活（如果是激活状态），然后删除文件
      if (preset.active) await handleDeactivate();
      const resp = await fetch(`/api/prompt-lab/presets/${preset.id}`, {
        method: "DELETE",
      });
      if (!resp.ok) { setError("删除失败"); return; }
      await loadPresets();
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  };

  // ── 新建预设 ──

  const handleNewPreset = () => {
    setEditingPreset({ id: "", name: "", icon: "bar-chart", description: "", active: false });
    setEditName("");
    setEditIcon("bar-chart");
    setEditDesc("");
    setEditPrompt("你是数据分析师。数据分析按五阶段推进：\n\n理解字段：\n评估清洗：\n统计分析：\n撰写报告：\n持续交互：\n\n每次回复都要让用户知道：你做了什么、结果是什么、接下来可以做什么。\n不要只描述过程——要展示结果。不确定就问用户。");
  };

  const handleCreatePreset = async () => {
    if (!editName.trim()) return;
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/prompt-lab/presets/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName.trim(),
          icon: editIcon,
          description: editDesc.trim(),
          prompt: editPrompt,
        }),
      });
      const data = await resp.json();
      if (!data.ok) { setError(data.detail || "创建失败"); return; }
      await loadPresets();
      setEditingPreset(null);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  };

  // ── 模拟实验室 ──

  const handleOpenLab = async (baseId: string) => {
    const content = await loadPresetContent(baseId);
    setLabBase(baseId);
    setLabPrompt(content);
    setLabMessage("");
    setLabResult(null);
    setLabCompare(null);
    setShowLab(true);
  };

  const handleLabRun = async () => {
    setLabRunning(true);
    setError("");
    setLabCompare(null);
    try {
      const resp = await fetch("/api/prompt-lab/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt_md: labPrompt,
          messages: labMessage ? [{ role: "user", content: labMessage }] : [],
        }),
      });
      const data = await resp.json();
      if (data.ok) setLabResult(data);
      else setError(data.detail || "运行失败");
    } catch (e: any) { setError(e.message); }
    setLabRunning(false);
  };

  const handleLabCompare = async () => {
    setLabRunning(true);
    setError("");
    setLabResult(null);
    try {
      const baseContent = await loadPresetContent(labBase);
      const resp = await fetch("/api/prompt-lab/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseline_prompt: baseContent,
          current_prompt: labPrompt,
          messages: labMessage ? [{ role: "user", content: labMessage }] : [],
        }),
      });
      if (!resp.ok) { setError("对比请求失败 (" + resp.status + ")"); return; }
      const data = await resp.json();
      if (data?.ok) { setLabResult(data.current); setLabCompare(data); }
      else setError(data?.detail || "对比失败");
    } catch (e: any) { setError(e?.message || "网络错误"); }
    setLabRunning(false);
  };

  const handleLabSaveAsNew = () => {
    setEditingPreset({ id: "", name: "", icon: "bar-chart", description: "", active: false });
    setEditName("");
    setEditIcon("bar-chart");
    setEditDesc("");
    setEditPrompt(labPrompt);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <PanelHeader title="分析能力">
        <span className="text-ui-xs text-app-text-muted font-normal tracking-normal normal-case">
          选择预设方向，定制分析行为
        </span>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* ── 预设列表 ──────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Sparkles size={14} className="text-app-accent" />
            <span className="text-ui-sm font-medium text-app-text">预设场景</span>
            {presets.find((p) => p.active) && (
              <span className="text-ui-xs text-app-accent ml-1">
                · 当前: {presets.find((p) => p.active)?.name}
              </span>
            )}
          </div>

          <div className="space-y-2">
            {presets.map((p) => (
              <div
                key={p.id}
                className={`relative border rounded-lg overflow-hidden transition-colors ${
                  p.active
                    ? "border-app-accent bg-app-accent/5"
                    : "border-app-border bg-app-bg-secondary"
                }`}
              >
                {/* 启用中标记 */}
                {p.active && (
                  <div className="absolute top-0 right-0">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-bl-lg rounded-tr-lg bg-app-accent text-white text-ui-xs font-medium">
                      <CheckCircle2 size={10} />
                      启用中
                    </span>
                  </div>
                )}
                {/* 卡片头部 */}
                <div className="flex items-start gap-3 p-3">
                  <span className="text-xl shrink-0 mt-0.5">
                    {ICON_MAP[p.icon] || "📋"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-ui-sm font-medium text-app-text">
                        {p.name}
                      </span>
                      {p.id === "general" && (
                        <span className="text-ui-xs text-app-text-muted">默认</span>
                      )}
                    </div>
                    <p className="text-ui-xs text-app-text-muted leading-snug mt-0.5">
                      {p.description}
                    </p>
                    {/* 源码展开 */}
                    {expandedPresets.has(p.id) && (
                      <PresetSource id={p.id} />
                    )}
                  </div>
                </div>

                {/* 操作按钮 */}
                <div className="flex items-center gap-1 px-3 pb-2.5 flex-wrap">
                  {p.active ? (
                    <button
                      type="button" disabled={loading}
                      onClick={handleDeactivate}
                      className="px-2.5 py-1 text-ui-xs rounded bg-app-accent/10 text-app-accent hover:bg-app-accent/20 transition-colors cursor-pointer"
                    >
                      恢复默认
                    </button>
                  ) : (
                    <button
                      type="button" disabled={loading}
                      onClick={() => handleActivate(p.id)}
                      className="px-2.5 py-1 text-ui-xs rounded bg-app-accent text-white hover:bg-app-accent-hover transition-colors cursor-pointer"
                    >
                      使用
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => toggleExpand(p.id)}
                    className="px-2 py-1 text-ui-xs text-app-text-muted hover:text-app-text cursor-pointer flex items-center gap-0.5"
                  >
                    {expandedPresets.has(p.id) ? <EyeOff size={10} /> : <Eye size={10} />}
                    源码
                  </button>
                  <button
                    type="button"
                    onClick={() => handleStartEdit(p)}
                    className="px-2 py-1 text-ui-xs text-app-text-muted hover:text-app-text cursor-pointer flex items-center gap-0.5"
                  >
                    <Pencil size={10} />
                    编辑
                  </button>
                  {p.id !== "general" && (
                    <button
                      type="button" disabled={loading}
                      onClick={() => handleDelete(p)}
                      className="px-2 py-1 text-ui-xs text-app-text-muted hover:text-red-500 cursor-pointer flex items-center gap-0.5"
                    >
                      <Trash2 size={10} />
                      删除
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => handleOpenLab(p.id)}
                    className="px-2 py-1 text-ui-xs text-app-accent hover:underline cursor-pointer flex items-center gap-0.5 ml-auto"
                  >
                    <FlaskConical size={10} />
                    模拟
                  </button>
                </div>
              </div>
            ))}

            {/* 新建按钮 */}
            <button
              type="button"
              onClick={handleNewPreset}
              className="w-full border border-dashed border-app-border rounded-lg p-3 flex items-center justify-center gap-2 text-ui-sm text-app-text-muted hover:border-app-accent hover:text-app-accent transition-colors cursor-pointer"
            >
              <Plus size={14} />
              新建场景
            </button>
          </div>
        </div>

        {/* ── 模拟实验室 ────────────────────────────────────────── */}
        <div>
          <button
            onClick={() => setShowLab((v) => !v)}
            className="flex items-center gap-1.5 text-ui-sm text-app-text-muted hover:text-app-text cursor-pointer"
          >
            <FlaskConical size={14} className="text-app-accent" />
            提示词实验室
            {showLab ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>

          {showLab && (
            <div className="mt-2 space-y-3 p-3 border border-app-border rounded-lg bg-app-bg-secondary">
              <div className="text-ui-xs text-app-text-muted">
                基于「{presets.find((p) => p.id === labBase)?.name || labBase}」进行模拟调试
              </div>

              <textarea
                value={labPrompt}
                onChange={(e) => setLabPrompt(e.target.value)}
                rows={10}
                className="w-full bg-app-bg border border-app-border rounded p-3 text-ui-xs font-mono text-app-text resize-y focus:outline-none focus:border-app-accent"
              />

              <input
                type="text"
                value={labMessage}
                onChange={(e) => setLabMessage(e.target.value)}
                placeholder="测试消息（模拟用户输入，可选）"
                className="w-full bg-app-bg border border-app-border rounded px-3 py-2 text-ui-sm text-app-text focus:outline-none focus:border-app-accent"
              />

              <div className="flex items-center gap-2 flex-wrap">
                <ActionButton variant="primary" icon={Play} loading={labRunning} onClick={handleLabRun}>
                  试运行
                </ActionButton>
                <ActionButton variant="secondary" icon={GitCompare} disabled={labRunning} onClick={handleLabCompare}>
                  对比原版
                </ActionButton>
                <ActionButton variant="secondary" icon={Save} disabled={labRunning} onClick={handleLabSaveAsNew}>
                  保存为新场景
                </ActionButton>
              </div>

              {error && <StatusBanner type="error" message={error} />}

              {labResult && (
                <div className="bg-app-bg border border-app-border rounded p-3 max-h-48 overflow-y-auto">
                  <div className="text-ui-xs font-medium text-app-text-muted mb-1">运行结果</div>
                  {labResult.tool_calls?.length > 0 && (
                    <div className="text-ui-xs text-app-accent mb-1">
                      工具: {labResult.tool_calls.map((t) => t.name).join(", ")}
                    </div>
                  )}
                  <pre className="text-ui-xs text-app-text whitespace-pre-wrap leading-snug">
                    {(labResult.content || "").slice(0, 1000)}
                  </pre>
                </div>
              )}

              {labCompare && (
                <div className="bg-app-bg border border-app-border rounded p-3">
                  <div className="text-ui-xs font-medium text-app-text-muted mb-1">对比结果</div>
                  <div className="text-ui-xs text-app-text">
                    工具变化: {labCompare.diff.changed_paths.length > 0
                      ? labCompare.diff.changed_paths.join(", ") : "无变化"}
                    {" · "}相似度: {Math.round(labCompare.diff.similarity * 100)}%
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── 编辑弹窗 ── */}
        {editingPreset !== null && (
          <PresetEditor
            preset={editingPreset}
            name={editName} setName={setEditName}
            icon={editIcon} setIcon={setEditIcon}
            desc={editDesc} setDesc={setEditDesc}
            prompt={editPrompt} setPrompt={setEditPrompt}
            loading={loading}
            onSave={editingPreset.id ? handleSaveEdit : handleCreatePreset}
            onCancel={() => { setEditingPreset(null); setError(""); }}
            error={error}
          />
        )}
      </div>
    </div>
  );
}

// ── 源码展开组件 ────────────────────────────────────────────────

function PresetSource({ id }: { id: string }) {
  const [content, setContent] = useState("");
  useEffect(() => {
    fetch(`/api/prompt-lab/presets/${id}/content`)
      .then((r) => r.json())
      .then((d) => { if (d.ok) setContent(d.content); })
      .catch(() => {});
  }, [id]);

  if (!content) return <div className="text-ui-xs text-app-text-muted mt-1">加载中…</div>;

  return (
    <pre className="mt-2 p-2 bg-app-bg border border-app-border rounded text-ui-xs text-app-text-muted whitespace-pre-wrap max-h-32 overflow-y-auto leading-snug">
      {content.slice(0, 500)}{content.length > 500 ? "…" : ""}
    </pre>
  );
}

// ── 编辑弹窗 ────────────────────────────────────────────────────

function PresetEditor({
  preset, name, setName, icon, setIcon, desc, setDesc, prompt, setPrompt,
  loading, onSave, onCancel, error,
}: {
  preset: PresetInfo;
  name: string; setName: (v: string) => void;
  icon: string; setIcon: (v: string) => void;
  desc: string; setDesc: (v: string) => void;
  prompt: string; setPrompt: (v: string) => void;
  loading: boolean;
  onSave: () => void;
  onCancel: () => void;
  error: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onCancel}>
      <div
        className="bg-app-bg-secondary border border-app-border rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Pencil size={14} className="text-app-accent" />
            <span className="text-ui-sm font-medium text-app-text">
              {preset.id ? `编辑「${preset.name}」` : "新建场景"}
            </span>
          </div>

          <div>
            <label className="text-ui-xs text-app-text-muted block mb-1">名称</label>
            <input
              type="text" value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="场景名称"
              className="w-full bg-app-bg border border-app-border rounded px-3 py-2 text-ui-sm text-app-text focus:outline-none focus:border-app-accent"
            />
          </div>

          <div>
            <label className="text-ui-xs text-app-text-muted block mb-1">图标</label>
            <div className="flex gap-2">
              {Object.entries(ICON_MAP).map(([key, emoji]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setIcon(key)}
                  className={`w-10 h-10 rounded border text-lg flex items-center justify-center cursor-pointer transition-colors ${
                    icon === key ? "border-app-accent bg-app-accent/10" : "border-app-border hover:border-app-accent"
                  }`}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-ui-xs text-app-text-muted block mb-1">描述</label>
            <input
              type="text" value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="简短描述这个场景适合什么分析"
              className="w-full bg-app-bg border border-app-border rounded px-3 py-2 text-ui-sm text-app-text focus:outline-none focus:border-app-accent"
            />
          </div>

          <div>
            <label className="text-ui-xs text-app-text-muted block mb-1">提示词</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={14}
              className="w-full bg-app-bg border border-app-border rounded p-3 text-ui-xs font-mono text-app-text resize-y focus:outline-none focus:border-app-accent"
            />
          </div>

          {error && <StatusBanner type="error" message={error} />}

          <div className="flex items-center gap-2 justify-end">
            <button
              type="button" onClick={onCancel}
              className="px-3 py-1.5 text-ui-xs text-app-text-muted hover:text-app-text cursor-pointer"
            >
              取消
            </button>
            <ActionButton variant="primary" icon={Save} loading={loading} onClick={onSave} disabled={!name.trim()}>
              {preset.id ? "保存" : "创建"}
            </ActionButton>
          </div>
        </div>
      </div>
    </div>
  );
}
