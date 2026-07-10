import { useState, useEffect, useCallback } from "react";
import {
  Stethoscope,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  RefreshCw,
  Cpu,
  BookOpen,
  Send,
  User,
  Bot,
} from "lucide-react";
import { PanelHeader } from "../components/PanelHeader";

// ── 类型 ────────────────────────────────────────────────────────

interface HealthCheck {
  name: string;
  ok: boolean;
  detail: string;
  suggestions: string[];
}

interface HealthResponse {
  ok: boolean;
  total: number;
  passed: number;
  blocking_failed: boolean;
  checks: HealthCheck[];
  model_available: string;
  token_rate_tok_s: number;
}

interface DoctorStatus {
  meta_llm_configured: boolean;
  audits_dir: string;
  audits_exist: boolean;
}

type AuditTab = "methods" | "tools";

// ── 组件 ────────────────────────────────────────────────────────

export default function DoctorPanel() {
  // 健康检查
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  // 审计
  const [auditRunning, setAuditRunning] = useState<AuditTab | null>(null);
  const [auditMessage, setAuditMessage] = useState<string | null>(null);

  // Doctor 状态
  const [status, setStatus] = useState<DoctorStatus | null>(null);

  // ── 对话 ──
  interface ChatMsg {
    role: "user" | "doctor";
    content: string;
  }
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const sendChat = async () => {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;
    setChatInput("");
    await sendChatMessage(msg);
  };

  const sendChatMessage = async (msg: string) => {
    const userMsg: ChatMsg = { role: "user", content: msg };
    const updated = [...chatMessages, userMsg];
    setChatMessages(updated);
    setChatLoading(true);
    try {
      const history = updated.slice(-10).map((m) => ({
        role: m.role === "doctor" ? "assistant" : "user",
        content: m.content,
      }));
      const r = await fetch("/api/doctor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history }),
      });
      const d = (await r.json().catch(() => ({}))) as { reply?: string; detail?: string };
      if (!r.ok) throw new Error(d.detail || `请求失败 (${r.status})`);
      setChatMessages([...updated, { role: "doctor", content: d.reply || "(空回复)" }]);
    } catch (e: unknown) {
      setChatMessages([...updated, { role: "doctor", content: `❌ ${e instanceof Error ? e.message : "请求失败"}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  // ── 加载健康检查 ──
  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const r = await fetch("/api/doctor/health");
      if (!r.ok) throw new Error(`加载失败 (${r.status})`);
      const d = (await r.json()) as HealthResponse;
      setHealth(d);
    } catch (e: unknown) {
      setHealthError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // ── 加载审计列表 ──
  const loadAudits = useCallback(async () => {
    setAuditsLoading(true);
    try {
      const r = await fetch("/api/doctor/audits");
      if (!r.ok) throw new Error(`加载失败 (${r.status})`);
      const d = (await r.json()) as { audits: AuditItem[] };
      setAudits(d.audits || []);
    } catch {
      // 静默失败
    } finally {
      setAuditsLoading(false);
    }
  }, []);

  // ── 加载 Doctor 状态 ──
  const loadStatus = useCallback(async () => {
    try {
      const r = await fetch("/api/doctor/status");
      if (r.ok) {
        const d = (await r.json()) as DoctorStatus;
        setStatus(d);
      }
    } catch {
      // 静默
    }
  }, []);

  // 初始化
  useEffect(() => {
    loadHealth();
    loadStatus();
  }, [loadHealth, loadStatus]);

  // ── 触发审计 ──
  const triggerAudit = async (tab: AuditTab) => {
    setAuditRunning(tab);
    setAuditMessage(null);
    const endpoint = tab === "methods" ? "/api/doctor/audit/methods" : "/api/doctor/audit/tools";
    try {
      const r = await fetch(endpoint, { method: "POST" });
      const d = await r.json().catch(() => ({})) as { ok?: boolean; report_path?: string; detail?: string };
      if (!r.ok) {
        throw new Error(typeof d.detail === "string" ? d.detail : `审计失败 (${r.status})`);
      }
      setAuditMessage(`✅ 审计完成`);
      // 读取审计报告内容，直接喂给 Doctor 分析
      const reportName = d.report_path?.split("/").pop() || "";
      const tabLabel = tab === "methods" ? "方法库" : "工具箱";
      try {
        const r2 = await fetch(`/api/doctor/audits/${encodeURIComponent(reportName)}`);
        const d2 = await r2.json().catch(() => ({})) as { content?: string };
        const reportText = d2.content || "";
        const summary = reportText.length > 2000 ? reportText.slice(0, 2000) + "\n...(已截断)" : reportText;
        await sendChatMessage(`请分析下面这份${tabLabel}审计报告，用中文指出关键问题和改进建议：

${summary}`);
      } catch {
        await sendChatMessage(`我刚完成了${tabLabel}审计，请帮我分析结果。`);
      }
    } catch (e: unknown) {
      setAuditMessage(`❌ ${e instanceof Error ? e.message : "审计失败"}`);
    } finally {
      setAuditRunning(null);
    }
  };

  // ── 查看报告 ──
  const viewReport = async (name: string) => {
    setSelectedReport(name);
    setReportLoading(true);
    setReportContent(null);
    try {
      const r = await fetch(`/api/doctor/audits/${encodeURIComponent(name)}`);
      if (!r.ok) throw new Error(`加载失败 (${r.status})`);
      const d = (await r.json()) as { content: string };
      setReportContent(d.content);
    } catch (e: unknown) {
      setReportContent(`❌ ${e instanceof Error ? e.message : "加载失败"}`);
    } finally {
      setReportLoading(false);
    }
  };

  // ── 样式 ──
  const inputClass =
    "w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-sm text-app-text placeholder-app-text-muted outline-none focus:border-app-accent transition-colors duration-150";

  const btnClass =
    "flex items-center gap-2 px-3 py-1.5 text-ui-sm rounded border border-app-border bg-app-bg-secondary hover:bg-app-bg disabled:opacity-40 disabled:cursor-not-allowed text-app-text transition-colors cursor-pointer";

  const accentBtnClass =
    "flex items-center gap-2 px-4 py-2 bg-app-accent hover:bg-app-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-ui-base rounded transition-colors cursor-pointer";

  const okCount = health?.passed ?? 0;
  const totalCount = health?.total ?? 0;
  const hasBlocking = health?.blocking_failed ?? false;

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text">
      <PanelHeader title="Doctor" icon={<Stethoscope size={16} />}>
        <div className="flex items-center gap-2">
          {health && (
            <span className={`text-ui-xs ${hasBlocking ? "text-app-error" : health.ok ? "text-green-400" : "text-app-warning"}`}>
              健康 {okCount}/{totalCount}
            </span>
          )}
          <button
            onClick={() => triggerAudit("methods")} disabled={auditRunning !== null}
            className="px-2 py-0.5 text-ui-xs rounded border border-app-border/50 text-app-text-muted hover:text-app-accent hover:border-app-accent cursor-pointer disabled:opacity-50"
          >
            {auditRunning === "methods" ? <Loader2 size={11} className="animate-spin inline mr-0.5" /> : <BookOpen size={11} className="inline mr-0.5" />}
            审知识库
          </button>
          <button
            onClick={() => triggerAudit("tools")} disabled={auditRunning !== null}
            className="px-2 py-0.5 text-ui-xs rounded border border-app-border/50 text-app-text-muted hover:text-app-accent hover:border-app-accent cursor-pointer disabled:opacity-50"
          >
            {auditRunning === "tools" ? <Loader2 size={11} className="animate-spin inline mr-0.5" /> : <Cpu size={11} className="inline mr-0.5" />}
            审工具箱
          </button>
        </div>
      </PanelHeader>

      {/* ── 状态条（紧凑） ── */}
      {status && (
        <div className={`text-ui-xs px-3 py-1.5 border-b ${
          status.meta_llm_configured
            ? "border-green-500/30 bg-green-500/10 text-green-400"
            : "border-app-warning/30 bg-app-warning/10 text-app-warning"
        }`}>
          {status.meta_llm_configured
            ? "✅ LLM 连接可用"
            : "⚠️ LLM 未配置 — 请在「设置」中配置 LLM 连接。"}
        </div>
      )}

      {/* ══════ 对话区 ══════ */}
      <div className="flex-1 flex flex-col px-4 overflow-hidden">
        {/* 消息列表 — 撑满剩余空间 */}
        <div className="flex-1 overflow-y-auto space-y-2 py-3">
          {chatMessages.length === 0 && (
            <p className="text-ui-xs text-app-text-muted text-center py-8">
              💬 向 HaGoKu Doctor 提问 — 诊断问题、理解审计报告、获取维护建议。
            </p>
          )}
          {chatMessages.map((m, i) => (
            <div
              key={i}
              className={`flex gap-2 text-ui-xs ${
                m.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              {m.role === "doctor" && (
                <Bot size={14} className="text-app-accent shrink-0 mt-0.5" />
              )}
              <div
                className={`px-3 py-2 rounded max-w-[85%] whitespace-pre-wrap leading-relaxed ${
                  m.role === "user"
                    ? "bg-app-accent/20 text-app-text"
                    : "bg-app-bg-secondary border border-app-border text-app-text"
                }`}
              >
                {m.content}
              </div>
              {m.role === "user" && (
                <User size={14} className="text-app-text-muted shrink-0 mt-0.5" />
              )}
            </div>
          ))}
          {chatLoading && (
            <div className="flex gap-2 text-ui-xs">
              <Bot size={14} className="text-app-accent shrink-0 mt-0.5" />
              <div className="px-3 py-2 rounded bg-app-bg-secondary border border-app-border text-app-text-muted">
                <Loader2 size={12} className="animate-spin inline mr-1" />
                思考中…
              </div>
            </div>
          )}
        </div>

        {/* 输入框 */}
        <div className="flex gap-2 py-3">
          <input
            className={inputClass + " flex-1"}
            placeholder="向 Doctor 提问..."
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
            disabled={chatLoading}
          />
          <button
            onClick={sendChat}
            disabled={chatLoading || !chatInput.trim()}
            className={accentBtnClass}
          >
            {chatLoading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </div>
      </div>

    </div>
  );
}
