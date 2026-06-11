import React, { useState, useEffect } from "react";

interface DumpInfo {
  filename: string;
  seq: number;
  mtime: number;
}

interface LabResult {
  content: string;
  tool_calls: Array<{ name: string; arguments: string }>;
  tokens: number;
  model?: string;
}

const PromptLabPanel: React.FC = () => {
  const [prompt, setPrompt] = useState("");
  const [userMessage, setUserMessage] = useState("");
  const [result, setResult] = useState<LabResult | null>(null);
  const [compareBaseline, setCompareBaseline] = useState<LabResult | null>(null);
  const [dumps, setDumps] = useState<DumpInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [applyResult, setApplyResult] = useState("");

  useEffect(() => {
    fetch("/api/prompt-lab/dumps?limit=20")
      .then((r) => r.json())
      .then((d) => setDumps(d.dumps || []))
      .catch(() => {});
    // Load current prompt.md
    fetch("/api/prompt-lab/current-prompt")
      .then((r) => r.json())
      .then((d) => { if (d.content && !prompt) setPrompt(d.content); })
      .catch(() => {});
  }, []);

  const handleRun = async () => {
    setLoading(true);
    setError("");
    try {
      const resp = await fetch("/api/prompt-lab/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt_md: prompt,
          messages: userMessage ? [{ role: "user", content: userMessage }] : [],
        }),
      });
      const data = await resp.json();
      if (data.ok) setResult(data);
      else setError(data.detail || "Error");
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const handleCompare = async () => {
    setLoading(true);
    try {
      // Load current prompt.md as baseline
      const baselineResp = await fetch("/api/prompt-lab/current-prompt");
      const baselineData = await baselineResp.json();
      const resp = await fetch("/api/prompt-lab/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseline_prompt: baselineData.content || "",
          current_prompt: prompt,
          messages: userMessage ? [{ role: "user", content: userMessage }] : [],
        }),
      });
      const data = await resp.json();
      if (data.ok) {
        setResult(data.current);
        setCompareBaseline(data.baseline);
      }
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  return (
    <div className="prompt-lab-panel">
      <h2>Prompt Lab</h2>

      <div className="lab-editor">
        <label>Prompt (Markdown)</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={20}
          placeholder="输入或修改 prompt.md 内容..."
        />
      </div>

      <div className="lab-input">
        <label>测试消息（可选）</label>
        <input
          value={userMessage}
          onChange={(e) => setUserMessage(e.target.value)}
          placeholder="例如：分析 ROI 数据"
        />
      </div>

      <div className="lab-actions">
        <button onClick={handleRun} disabled={loading || !prompt}>
          {loading ? "运行中..." : "▶ 运行"}
        </button>
        <button onClick={handleCompare} disabled={loading || !prompt}>
          📋 对比原版
        </button>
        <button onClick={async () => {
          if (!confirm("确认应用 prompt.md？将先跑 gate 检查再写盘。")) return;
          setLoading(true);
          try {
            const resp = await fetch("/api/prompt-lab/apply", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ prompt_md: prompt }),
            });
            const data = await resp.json();
            setApplyResult(data.gate_output || data.message || "已应用");
          } catch (e: any) { setError(e.message); }
          setLoading(false);
        }} disabled={loading || !prompt}>
          💾 应用
        </button>
        <button onClick={async () => {
          setLoading(true);
          try {
            const resp = await fetch("/api/prompt-lab/audit-lessons", { method: "POST" });
            const data = await resp.json();
            setApplyResult("审计完成: " + (data.report_path || "ok"));
          } catch (e: any) { setError(e.message); }
          setLoading(false);
        }} disabled={loading}>
          🔍 审 lessons
        </button>
      </div>

      {error && <div className="lab-error">{error}</div>}
      {applyResult && <div className="lab-apply-result"><pre>{applyResult}</pre></div>}

      {result && (
        <div className="lab-result">
          <h3>结果</h3>
          <p>Tokens: {result.tokens} | Model: {result.model || "pipeline"}</p>
          <pre>{result.content}</pre>
          {result.tool_calls?.length > 0 && (
            <div>
              <h4>Tool Calls</h4>
              {result.tool_calls.map((tc, i) => (
                <div key={i}>
                  → {tc.name}({tc.arguments?.substring(0, 200)})
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {compareBaseline && (
        <div className="lab-compare">
          <h3>对比原版</h3>
          <p>Baseline tokens: {compareBaseline.tokens}</p>
          <pre>{compareBaseline.content?.substring(0, 500)}</pre>
        </div>
      )}

      <div className="lab-dumps">
        <h3>历史 Dump</h3>
        {dumps.map((d) => (
          <div key={d.filename} className="dump-item">
            {d.filename}
          </div>
        ))}
      </div>
    </div>
  );
};

export default PromptLabPanel;
