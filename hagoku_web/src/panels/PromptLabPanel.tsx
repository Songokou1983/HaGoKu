import { useState, useEffect } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { ActionButton } from "../components/ActionButton";
import { StatusBanner } from "../components/StatusBanner";
import {
  Play,
  GitCompare,
  Save,
  ScrollText,
  FileJson,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────

interface DumpInfo {
  filename: string;
  seq: number;
  mtime: number;
}

interface DumpDetail {
  ok: boolean;
  filename?: string;
  model?: string;
  stage?: string;
  messages?: Array<{ role: string; content: string }>;
  tools?: string[];
}

interface LabResult {
  content: string;
  tool_calls: Array<{ name: string; arguments: string }>;
  tokens: number;
  model?: string;
}

interface CompareResult {
  ok: boolean;
  baseline: LabResult;
  current: LabResult;
  diff: {
    changed_paths: string[];
    similarity: number;
    baseline_tokens: number;
    current_tokens: number;
  };
}

type LabState =
  | "idle"
  | "dirty"
  | "running"
  | "result"
  | "compare"
  | "apply_ok"
  | "error";

// ── Component ──────────────────────────────────────────────────────

export default function PromptLabPanel() {
  // Editor
  const [prompt, setPrompt] = useState("");
  const [userMessage, setUserMessage] = useState("");
  const [lineCount, setLineCount] = useState(0);
  const [charCount, setCharCount] = useState(0);

  // State machine
  const [labState, setLabState] = useState<LabState>("idle");

  // Results
  const [result, setResult] = useState<LabResult | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(
    null,
  );
  const [applyGateOutput, setApplyGateOutput] = useState("");
  const [auditResult, setAuditResult] = useState("");

  // Dumps
  const [dumps, setDumps] = useState<DumpInfo[]>([]);
  const [selectedDump, setSelectedDump] = useState<DumpDetail | null>(null);
  const [selectedDumpFilename, setSelectedDumpFilename] = useState<string | null>(null);
  const [dumpLoading, setDumpLoading] = useState(false);

  // UI tabs
  const [resultTab, setResultTab] = useState<"output" | "compare" | "gate" | "messages">("output");

  // Error
  const [error, setError] = useState("");

  // ── Load initial data ──────────────────────────────────────────

  useEffect(() => {
    fetch("/api/prompt-lab/dumps?limit=20")
      .then((r) => r.json())
      .then((d) => setDumps(d.dumps || []))
      .catch(() => {});
    fetch("/api/prompt-lab/current-prompt")
      .then((r) => r.json())
      .then((d) => {
        if (d.content && !prompt) {
          setPrompt(d.content);
          updateStats(d.content);
        }
      })
      .catch(() => {});
  }, []);

  const updateStats = (text: string) => {
    setLineCount(text.split("\n").length);
    setCharCount(text.length);
  };

  const handlePromptChange = (v: string) => {
    setPrompt(v);
    updateStats(v);
    if (labState === "idle") setLabState("dirty");
  };

  // ── Actions ────────────────────────────────────────────────────

  const handleRun = async () => {
    setLabState("running");
    setError("");
    setResultTab("output");
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
      if (data.ok) {
        setResult(data);
        setLabState("result");
      } else {
        setError(data.detail || "运行失败");
        setLabState("error");
      }
    } catch (e: any) {
      setError(e.message);
      setLabState("error");
    }
  };

  const handleCompare = async () => {
    setLabState("running");
    setError("");
    setResultTab("compare");
    try {
      const baselineResp = await fetch("/api/prompt-lab/current-prompt");
      const baselineData = await baselineResp.json();
      const resp = await fetch("/api/prompt-lab/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseline_prompt: baselineData.content || "",
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
        setLabState("compare");
      } else {
        setError(data.detail || "对比失败");
        setLabState("error");
      }
    } catch (e: any) {
      setError(e.message);
      setLabState("error");
    }
  };

  const handleApply = async () => {
    if (!confirm("确认应用 prompt.md？将先跑 gate 检查再写盘。")) return;
    setLabState("running");
    setError("");
    try {
      const resp = await fetch("/api/prompt-lab/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt_md: prompt }),
      });
      const data = await resp.json();
      setApplyGateOutput(data.gate_output || data.message || "已应用");
      setLabState("apply_ok");
      setResultTab("gate");
    } catch (e: any) {
      setError(e.message);
      setLabState("error");
    }
  };

  const handleAudit = async () => {
    setLabState("running");
    setError("");
    try {
      const resp = await fetch("/api/prompt-lab/audit-lessons", {
        method: "POST",
      });
      const data = await resp.json();
      setAuditResult(
        "审计完成: " + (data.report_path || JSON.stringify(data)),
      );
      setLabState("result");
    } catch (e: any) {
      setError(e.message);
      setLabState("error");
    }
  };

  const handleLoadDump = async (filename: string) => {
    setDumpLoading(true);
    setSelectedDumpFilename(filename);
    try {
      const resp = await fetch(`/api/prompt-lab/dump/${filename}`);
      const data = await resp.json();
      setSelectedDump(data);
      setResultTab("messages");
    } catch {
      setError("无法加载 dump");
    }
    setDumpLoading(false);
  };

  const handleLoadDumpAsMessage = () => {
    if (!selectedDump?.messages) return;
    const lastUser = [...selectedDump.messages]
      .reverse()
      .find((m) => m.role === "user");
    if (lastUser?.content) {
      setUserMessage(lastUser.content);
    }
  };

  const isBusy = labState === "running";

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <PanelHeader title="Prompt Lab">
        <span className="text-ui-xs text-app-text-muted font-normal tracking-normal normal-case">
          提示词实验室
        </span>
        {labState === "dirty" && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-ui-xs bg-app-warning/15 text-app-warning font-medium">
            已修改
          </span>
        )}
        {labState === "apply_ok" && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-ui-xs bg-app-success/15 text-app-success font-medium">
            已应用
          </span>
        )}
      </PanelHeader>

      <div className="flex-1 overflow-y-auto">
        {/* ── Toolbar ────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-app-border">
          <ActionButton
            variant="primary"
            icon={Play}
            loading={isBusy}
            onClick={handleRun}
          >
            试运行
          </ActionButton>
          <ActionButton
            variant="secondary"
            icon={GitCompare}
            disabled={isBusy || !prompt}
            onClick={handleCompare}
          >
            对比磁盘版
          </ActionButton>
          <div className="flex-1" />
          <ActionButton
            variant="danger"
            icon={Save}
            disabled={isBusy || !prompt}
            onClick={handleApply}
          >
            应用
          </ActionButton>
          <ActionButton
            variant="ghost"
            icon={ScrollText}
            disabled={isBusy}
            onClick={handleAudit}
          >
            审计 lessons
          </ActionButton>
        </div>

        {/* ── Error banner ───────────────────────────────────────── */}
        {error && (
          <div className="px-4 pt-2">
            <StatusBanner
              variant="error"
              message={error}
              dismissible
            />
          </div>
        )}

        {/* ── Main layout: lg:grid-cols-2 ───────────────────────── */}
        <div className="lg:grid lg:grid-cols-2 lg:divide-x lg:divide-app-border">
          {/* Left: Editor + test message */}
          <div className="flex flex-col min-h-0">
            <div className="p-3 border-b border-app-border">
              <label className="text-ui-xs text-app-text-muted font-medium mb-1 block">
                Prompt (Markdown) · {lineCount} 行 · {charCount} 字
              </label>
              <textarea
                value={prompt}
                onChange={(e) => handlePromptChange(e.target.value)}
                rows={18}
                className="w-full bg-app-bg-secondary border border-app-border rounded px-3 py-2
                  text-ui-xs text-app-text font-mono placeholder-app-text-muted resize-y
                  focus:outline-none focus:border-app-accent transition-colors"
                placeholder="输入或修改 prompt.md 内容..."
                spellCheck={false}
              />
            </div>
            <div className="p-3">
              <label className="text-ui-xs text-app-text-muted font-medium mb-1 block">
                测试消息（可选）
              </label>
              <textarea
                value={userMessage}
                onChange={(e) => setUserMessage(e.target.value)}
                rows={3}
                className="w-full bg-app-bg-secondary border border-app-border rounded px-3 py-2
                  text-ui-xs text-app-text placeholder-app-text-muted resize-none
                  focus:outline-none focus:border-app-accent transition-colors"
                placeholder="例如：分析 ROI 数据"
              />
            </div>
          </div>

          {/* Right: Results */}
          <div className="flex flex-col min-h-0">
            {/* Tabs */}
            <div className="flex items-center border-b border-app-border px-3">
              {(["output", "compare", "gate", "messages"] as const).map(
                (tab) => (
                  <button
                    key={tab}
                    onClick={() => setResultTab(tab)}
                    className={`px-3 py-2 text-ui-xs font-medium transition-colors duration-150 cursor-pointer border-b-2
                      ${
                        resultTab === tab
                          ? "border-app-accent text-app-accent"
                          : "border-transparent text-app-text-muted hover:text-app-text"
                      }`}
                  >
                    {tab === "output" && "输出"}
                    {tab === "compare" && "对比"}
                    {tab === "gate" && "Gate"}
                    {tab === "messages" && "Messages"}
                  </button>
                ),
              )}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-3">
              {/* Output tab */}
              {resultTab === "output" && result && (
                <div className="space-y-2">
                  <div className="text-ui-xs text-app-text-muted">
                    Tokens: {result.tokens} | Model: {result.model || "pipeline"}
                  </div>
                  <pre className="text-ui-xs text-app-text whitespace-pre-wrap leading-relaxed bg-app-bg-secondary border border-app-border rounded p-2">
                    {result.content}
                  </pre>
                  {result.tool_calls?.length > 0 && (
                    <div>
                      <div className="text-ui-xs text-app-text-muted font-medium mb-1">
                        Tool Calls
                      </div>
                      {result.tool_calls.map((tc, i) => (
                        <div
                          key={i}
                          className="text-ui-xs text-app-accent font-mono bg-app-bg-secondary border border-app-border rounded px-2 py-1 mb-1"
                        >
                          {tc.name}(
                          {tc.arguments?.substring(0, 200)})
                        </div>
                      ))}
                    </div>
                  )}
                  {!result && (
                    <div className="text-ui-xs text-app-text-muted italic">
                      点击「试运行」查看 LLM 输出
                    </div>
                  )}
                </div>
              )}

              {/* Compare tab */}
              {resultTab === "compare" && compareResult && (
                <div className="space-y-2">
                  <div className="text-ui-xs text-app-text-muted">
                    相似度: {(compareResult.diff.similarity * 100).toFixed(1)}%
                    | 变化路径: {compareResult.diff.changed_paths.join(", ") || "无"}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <div className="text-ui-xs text-app-text-muted font-medium mb-1">
                        磁盘版 ({compareResult.diff.baseline_tokens} tokens)
                      </div>
                      <pre className="text-ui-xs text-app-text-muted whitespace-pre-wrap leading-relaxed bg-app-bg-secondary border border-app-border rounded p-2 max-h-48 overflow-y-auto">
                        {compareResult.baseline.content?.substring(0, 500)}
                      </pre>
                    </div>
                    <div>
                      <div className="text-ui-xs text-app-text-muted font-medium mb-1">
                        当前 ({compareResult.diff.current_tokens} tokens)
                      </div>
                      <pre className="text-ui-xs text-app-text whitespace-pre-wrap leading-relaxed bg-app-bg-secondary border border-app-border rounded p-2 max-h-48 overflow-y-auto">
                        {compareResult.current.content?.substring(0, 500)}
                      </pre>
                    </div>
                  </div>
                </div>
              )}

              {/* Gate tab — apply result (CO-09: separate from audit) */}
              {resultTab === "gate" && (
                <div className="space-y-2">
                  {applyGateOutput ? (
                    <pre className="text-ui-xs text-app-text whitespace-pre-wrap leading-relaxed bg-app-bg-secondary border border-app-border rounded p-2">
                      {applyGateOutput}
                    </pre>
                  ) : (
                    <div className="text-ui-xs text-app-text-muted italic">
                      应用 prompt.md 后查看 gate 输出
                    </div>
                  )}
                </div>
              )}

              {/* Messages tab — dump messages preview */}
              {resultTab === "messages" && (
                <div className="space-y-2">
                  {selectedDump ? (
                    <>
                      <div className="text-ui-xs text-app-text-muted">
                        Model: {selectedDump.model || "N/A"} | Stage:{" "}
                        {selectedDump.stage || "N/A"} |{" "}
                        {selectedDump.messages?.length || 0} 条消息
                      </div>
                      <button
                        onClick={handleLoadDumpAsMessage}
                        className="text-ui-xs text-app-accent hover:underline cursor-pointer"
                      >
                        载入最后一条 user 消息为测试消息
                      </button>
                      <div className="space-y-1 max-h-64 overflow-y-auto">
                        {(selectedDump.messages || []).map(
                          (m: any, i: number) => (
                            <div
                              key={i}
                              className={`text-ui-xs rounded px-2 py-1 border border-app-border/40
                                ${
                                  m.role === "user"
                                    ? "bg-app-accent/10 text-app-accent"
                                    : m.role === "assistant"
                                      ? "bg-app-bg-secondary text-app-text"
                                      : "bg-transparent text-app-text-muted"
                                }`}
                            >
                              <span className="font-medium mr-1">
                                [{m.role}]
                              </span>
                              {typeof m.content === "string"
                                ? m.content.substring(0, 200)
                                : JSON.stringify(m.content).substring(0, 200)}
                            </div>
                          ),
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="text-ui-xs text-app-text-muted italic">
                      选择下方 dump 文件查看消息
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Audit result (separate from apply, CO-09) ──────────── */}
        {auditResult && (
          <div className="border-t border-app-border px-4 py-3">
            <div className="text-ui-xs text-app-text-muted font-medium mb-1 flex items-center gap-1">
              <ScrollText size={12} />
              审计结果
            </div>
            <pre className="text-ui-xs text-app-text whitespace-pre-wrap leading-relaxed bg-app-bg-secondary border border-app-border rounded p-2">
              {auditResult}
            </pre>
          </div>
        )}

        {/* ── Dump list ──────────────────────────────────────────── */}
        <div className="border-t border-app-border px-4 py-3">
          <div className="text-ui-xs text-app-text-muted font-medium mb-2 flex items-center gap-1">
            <FileJson size={12} />
            历史 Dump
            {dumps.length === 0 && (
              <span className="text-app-text-muted/60 font-normal ml-1">
                — 设置 HAGOKU_DUMP_LLM=1 开启
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {dumps.map((d) => (
              <button
                key={d.filename}
                onClick={() => handleLoadDump(d.filename)}
                disabled={dumpLoading}
                className={`px-2 py-1 rounded text-ui-xs font-mono transition-colors duration-150 cursor-pointer border
                  ${
                    selectedDumpFilename === d.filename
                      ? "border-app-accent text-app-accent bg-app-accent/10"
                      : "border-app-border text-app-text-muted hover:text-app-text hover:border-app-accent/50"
                  }`}
              >
                {d.filename}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
