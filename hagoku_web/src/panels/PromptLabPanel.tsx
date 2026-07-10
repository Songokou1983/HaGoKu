import { useState, useEffect } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { ActionButton } from "../components/ActionButton";
import { StatusBanner } from "../components/StatusBanner";
import {
  Play,
  GitCompare,
  Save,
  ChevronDown,
  ChevronRight,
  Sparkles,
  CheckCircle2,
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
  diff: {
    changed_paths: string[];
    similarity: number;
  };
}

// ── Icons ──────────────────────────────────────────────────────────

const ICON_MAP: Record<string, string> = {
  "bar-chart": "📊",
  "trending-up": "📈",
  "shopping-cart": "🛒",
};

// ── Component ──────────────────────────────────────────────────────

export default function PromptLabPanel() {
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [activeId, setActiveId] = useState("");
  const [loading, setLoading] = useState(false);

  // Editor (collapsed by default)
  const [showEditor, setShowEditor] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [userMessage, setUserMessage] = useState("");

  // Results
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<LabResult | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState("");

  // ── Load presets ──────────────────────────────────────────────

  const loadPresets = async () => {
    try {
      const r = await fetch("/api/prompt-lab/presets");
      const d = await r.json();
      setPresets(d.presets || []);
      const active = (d.presets || []).find((p: PresetInfo) => p.active);
      setActiveId(active?.id || "");
    } catch {}
  };

  useEffect(() => {
    loadPresets();
  }, []);

  const handleActivate = async (id: string) => {
    setLoading(true);
    try {
      // If clicking the already-active preset, deactivate (back to default)
      const targetId = id === activeId ? "" : id;
      await fetch("/api/prompt-lab/presets/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: targetId }),
      });
      await loadPresets();
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  // ── Editor actions ────────────────────────────────────────────

  const handleRun = async () => {
    setRunning(true);
    setError("");
    setCompareResult(null);
    try {
      const resp = await fetch("/api/prompt-lab/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt_md: prompt,
          messages: userMessage
            ? [{ role: "user", content: userMessage }]
            : [],
        }),
      });
      const data = await resp.json();
      if (data.ok) setResult(data);
      else setError(data.detail || "运行失败");
    } catch (e: any) {
      setError(e.message);
    }
    setRunning(false);
  };

  const handleCompare = async () => {
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const baseResp = await fetch("/api/prompt-lab/current-prompt");
      const baseData = await baseResp.json();
      const resp = await fetch("/api/prompt-lab/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseline_prompt: baseData.content || "",
          current_prompt: prompt,
          messages: userMessage
            ? [{ role: "user", content: userMessage }]
            : [],
        }),
      });
      const data = await resp.json();
      if (data.ok) {
        setResult(data.current);
        setCompareResult(data);
      } else setError(data.detail || "对比失败");
    } catch (e: any) {
      setError(e.message);
    }
    setRunning(false);
  };

  const handleApply = async () => {
    if (!confirm("应用后将覆盖当前预设的 prompt，确认？")) return;
    setRunning(true);
    setError("");
    try {
      const resp = await fetch("/api/prompt-lab/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt_md: prompt }),
      });
      const data = await resp.json();
      if (!data.ok) setError(data.detail || "应用失败");
    } catch (e: any) {
      setError(e.message);
    }
    setRunning(false);
  };

  const loadPresetContent = async (id: string) => {
    try {
      const r = await fetch(`/api/prompt-lab/presets/${id}/content`);
      const d = await r.json();
      if (d.ok) setPrompt(d.content);
    } catch {}
  };

  const handleEditPreset = async (id: string) => {
    await loadPresetContent(id);
    setShowEditor(true);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <PanelHeader title="分析能力">
        <span className="text-ui-xs text-app-text-muted font-normal tracking-normal normal-case">
          选择预设方向，定制分析行为
        </span>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
        {/* ── 预设卡片 ──────────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Sparkles size={14} className="text-app-accent" />
            <span className="text-ui-sm font-medium text-app-text">预设场景</span>
            {activeId && (
              <span className="text-ui-xs text-app-text-muted ml-1">
                · 当前: {presets.find((p) => p.id === activeId)?.name}
              </span>
            )}
          </div>
          <p className="text-ui-xs text-app-text-muted mb-3 leading-snug">
            选择一个预设后，后续所有分析自动按该方向执行。选「通用」恢复默认。
          </p>

          {presets.length === 0 && (
            <div className="text-ui-xs text-app-text-muted py-2">加载中…</div>
          )}

          <div className="space-y-2">
            {presets.map((p) => (
              <div
                key={p.id}
                className={`border rounded-lg p-3 transition-colors ${
                  p.active
                    ? "border-app-accent bg-app-accent/5"
                    : "border-app-border bg-app-bg-secondary hover:border-app-accent/50"
                }`}
              >
                <div className="flex items-start gap-3">
                  <span className="text-xl shrink-0 mt-0.5">
                    {ICON_MAP[p.icon] || "📋"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-ui-sm font-medium text-app-text">
                        {p.name}
                      </span>
                      {p.active && (
                        <CheckCircle2 size={12} className="text-app-accent shrink-0" />
                      )}
                    </div>
                    <p className="text-ui-xs text-app-text-muted leading-snug mt-0.5">
                      {p.description}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => handleActivate(p.id)}
                    className={`shrink-0 px-3 py-1 text-ui-xs rounded transition-colors cursor-pointer ${
                      p.active
                        ? "bg-app-accent/10 text-app-accent hover:bg-app-accent/20"
                        : "bg-app-accent text-white hover:bg-app-accent-hover"
                    }`}
                  >
                    {p.active ? "恢复默认" : "使用"}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => handleEditPreset(p.id)}
                  className="mt-2 text-ui-xs text-app-text-muted hover:text-app-accent cursor-pointer"
                >
                  查看 / 编辑源码 →
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* ── 编辑器（折叠） ────────────────────────────────────── */}
        <div>
          <button
            onClick={() => setShowEditor((v) => !v)}
            className="flex items-center gap-1.5 text-ui-xs text-app-text-muted hover:text-app-text cursor-pointer mb-2"
          >
            {showEditor ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            高级：编辑 Prompt 源码
          </button>

          {showEditor && (
            <div className="space-y-3">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={12}
                className="w-full bg-app-bg-secondary border border-app-border rounded p-3 text-ui-xs font-mono text-app-text resize-y focus:outline-none focus:border-app-accent"
                placeholder="在此编辑 prompt…"
              />
              <input
                type="text"
                value={userMessage}
                onChange={(e) => setUserMessage(e.target.value)}
                placeholder="测试消息（可选）"
                className="w-full bg-app-bg-secondary border border-app-border rounded px-3 py-2 text-ui-sm text-app-text focus:outline-none focus:border-app-accent"
              />

              <div className="flex items-center gap-2">
                <ActionButton
                  variant="primary"
                  icon={Play}
                  loading={running}
                  onClick={handleRun}
                >
                  试运行
                </ActionButton>
                <ActionButton
                  variant="secondary"
                  icon={GitCompare}
                  disabled={running || !prompt}
                  onClick={handleCompare}
                >
                  对比原版
                </ActionButton>
                <ActionButton
                  variant="secondary"
                  icon={Save}
                  disabled={running || !prompt}
                  onClick={handleApply}
                >
                  应用
                </ActionButton>
              </div>

              {error && <StatusBanner type="error" message={error} />}

              {result && (
                <div className="bg-app-bg-secondary border border-app-border rounded p-3 max-h-64 overflow-y-auto">
                  <div className="text-ui-xs font-medium text-app-text-muted mb-1">
                    试运行结果
                  </div>
                  {result.tool_calls?.length > 0 && (
                    <div className="text-ui-xs text-app-accent mb-1">
                      工具调用: {result.tool_calls.map((t) => t.name).join(", ")}
                    </div>
                  )}
                  <pre className="text-ui-xs text-app-text whitespace-pre-wrap leading-snug">
                    {(result.content || "").slice(0, 1500)}
                  </pre>
                </div>
              )}

              {compareResult && (
                <div className="bg-app-bg-secondary border border-app-border rounded p-3">
                  <div className="text-ui-xs font-medium text-app-text-muted mb-1">
                    对比结果
                  </div>
                  <div className="text-ui-xs text-app-text">
                    工具调用变化:{" "}
                    {compareResult.diff.changed_paths.length > 0
                      ? compareResult.diff.changed_paths.join(", ")
                      : "无变化"}
                  </div>
                  <div className="text-ui-xs text-app-text-muted">
                    相似度: {Math.round(compareResult.diff.similarity * 100)}%
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
