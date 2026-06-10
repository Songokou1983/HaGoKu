import { useState, useEffect, useCallback } from "react";
import {
  Globe,
  Cpu,
  Key,
  Save,
  CheckCircle2,
  Loader2,
  AlertCircle,
  SlidersHorizontal,
  ChevronDown,
  ChevronRight,
  Zap,
  XCircle,
} from "lucide-react";
import { PanelHeader } from "../components/PanelHeader";
import { Field } from "../components/FormField";

/** 接口返回的完整 llm 片段（含 sub_model，用于判断是否曾拆成两个名字） */
interface LlmConfigPayload {
  base_url: string;
  main_model: string;
  sub_model: string;
  api_key_configured: boolean;
}

/** 表单里只编辑这三项；本页不提供第二格模型名 */
interface LlmFormState {
  base_url: string;
  main_model: string;
  api_key_configured: boolean;
}

interface ConfigResponse {
  llm: Partial<LlmConfigPayload> & Record<string, unknown>;
}

type TestStatus = "idle" | "testing" | "ok" | "fail";

const emptyLlm: LlmFormState = {
  base_url: "",
  main_model: "",
  api_key_configured: false,
};


function normalizeLlmFromApi(raw: Record<string, unknown>): LlmConfigPayload {
  const base_url = typeof raw.base_url === "string" ? raw.base_url : "";
  const api_key_configured = typeof raw.api_key_configured === "boolean" ? raw.api_key_configured : false;
  const model = typeof raw.model === "string" ? raw.model : "";
  return { base_url, main_model: model, sub_model: "", api_key_configured };
}

function formFromNormalized(n: LlmConfigPayload): LlmFormState {
  return {
    base_url: n.base_url,
    main_model: n.main_model,
    api_key_configured: n.api_key_configured,
  };
}

export default function SettingsPanel() {
  const [llm, setLlm] = useState<LlmFormState>(emptyLlm);
  const [metaUrl, setMetaUrl] = useState("");
  const [metaModel, setMetaModel] = useState("");
  const [metaKey, setMetaKey] = useState("");
      const [apiKeyInput, setApiKeyInput] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  // 测试连接
  const [testStatus, setTestStatus] = useState<TestStatus>("idle");
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testTime, setTestTime] = useState<string | null>(null);
  const [testStatusMeta, setTestStatusMeta] = useState<TestStatus>("idle");
  const [testMessageMeta, setTestMessageMeta] = useState<string | null>(null);
  const [testTimeMeta, setTestTimeMeta] = useState<string | null>(null);

  const loadConfig = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    fetch("/api/config")
      .then(async (r) => {
        if (!r.ok) throw new Error(`加载失败 (${r.status})`);
        return r.json() as Promise<ConfigResponse>;
      })
      .then((d) => {
        const raw = (d.llm ?? {}) as Record<string, unknown>;
        if (Object.keys(raw).length) {
          const n = normalizeLlmFromApi(raw);
          const metaFromApi = (d.meta_llm as any)?.model || "";
          setMetaModel(metaFromApi);
          setLlm(formFromNormalized(n));
          if (distinct) {
            setAdvancedLlmOpen(true);
            setSubModelQuick(n.sub_model.trim());
          } else {
            setSubModelQuick("");
            try {
              setAdvancedLlmOpen(localStorage.getItem("") === "1");
            } catch {
              setAdvancedLlmOpen(false);
            }
          }
        } else {
          setLlm(emptyLlm);
          setSubModelQuick("");
          try {
            setAdvancedLlmOpen(localStorage.getItem("") === "1");
          } catch {
            setAdvancedLlmOpen(false);
          }
        }
      })
      .catch((e: unknown) => {
        setLoadError(e instanceof Error ? e.message : "无法加载配置");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const handleTest = async () => {
    setTestStatus("testing");
    setTestMessage(null);
    setTestTime(null);
    try {
      const r = await fetch("/api/config/llm/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: llm.base_url.trim(),
          model: llm.main_model.trim(),
          api_key: apiKeyInput.trim(),
        }),
      });
      const d = (await r.json().catch(() => ({}))) as { ok?: boolean; reply?: string; detail?: string };
      if (!r.ok) {
        const msg = typeof d.detail === "string" ? d.detail : `连接失败 (${r.status})`;
        throw new Error(msg);
      }
      setTestStatus("ok");
      setTestMessage(d.reply?.slice(0, 120) || "模型响应正常");
      setTestTime(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      setTestStatus("fail");
      setTestMessage(e instanceof Error ? e.message : "连接失败");
      setTestTime(new Date().toLocaleTimeString());
    }
  };

  const handleTestMeta = async () => {
    const hasSome = !!(metaUrl.trim() || metaModel.trim() || metaKey.trim());
    const hasAll = !!(metaUrl.trim() && metaModel.trim() && metaKey.trim());
    if (hasSome && !hasAll) {
      setTestStatusMeta("fail");
      setTestMessageMeta("填了部分字段——要填就三项全填，要不全空复用主 LLM");
      setTestTimeMeta(new Date().toLocaleTimeString());
      return;
    }
    setTestStatusMeta("testing");
    setTestMessageMeta(null);
    setTestTimeMeta(null);
    const url = hasAll ? metaUrl.trim() : llm.base_url.trim();
    const model = hasAll ? metaModel.trim() : llm.main_model.trim();
    const key = hasAll ? metaKey.trim() : apiKeyInput.trim();
    try {
      const r = await fetch("/api/config/llm/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: url, model, api_key: key }),
      });
      const d = (await r.json().catch(() => ({}))) as { ok?: boolean; reply?: string; detail?: string };
      if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : `连接失败 (${r.status})`);
      setTestStatusMeta("ok");
      setTestMessageMeta(d.reply?.slice(0, 120) || "模型响应正常");
      setTestTimeMeta(new Date().toLocaleTimeString());
    } catch (e: unknown) {
      setTestStatusMeta("fail");
      setTestMessageMeta(e instanceof Error ? e.message : "连接失败");
      setTestTimeMeta(new Date().toLocaleTimeString());
    }
  };

  const handleSaveMeta = async () => {
    const hasSome = !!(metaUrl.trim() || metaModel.trim() || metaKey.trim());
    const hasAll = !!(metaUrl.trim() && metaModel.trim() && metaKey.trim());
    if (hasSome && !hasAll) {
      setSaveError("Doctor 填了部分字段——要填就三项全填，要不填就全部留空");
      return;
    }
    setSaving(true);
    try {
      const r = await fetch("/api/config/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: llm.base_url.trim(),
          model: llm.main_model.trim(),
          api_key: apiKeyInput.trim(),
          meta_base_url: metaUrl.trim(),
          meta_model: metaModel.trim(),
          meta_api_key: metaKey.trim(),
        }),
      });
      const d = (await r.json().catch(() => ({}))) as { detail?: string; hint?: string; llm?: LlmConfigPayload };
      if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : `保存失败 (${r.status})`);
      setSaved(true);
      setSaveHint(typeof d.hint === "string" ? d.hint : null);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    setSaveError(null);
    setSaveHint(null);
    setSaved(false);
    setSaving(true);
    try {
      const r = await fetch("/api/config/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: llm.base_url.trim(),
          main_model: llm.main_model.trim(),
          api_key: apiKeyInput.trim(),

        }),
      });
      const d = (await r.json().catch(() => ({}))) as {
        detail?: string;
        hint?: string;
        llm?: LlmConfigPayload;
      };
      if (!r.ok) {
        const msg = typeof d.detail === "string" ? d.detail : `保存失败 (${r.status})`;
        throw new Error(msg);
      }
      if (d.llm) {
        const n = normalizeLlmFromApi(d.llm as unknown as Record<string, unknown>);
        setLlm(formFromNormalized(n));
        if (distinct) {
          setAdvancedLlmOpen(true);
          setSubModelQuick(n.sub_model.trim());
        } else {
          setSubModelQuick("");
        }
      }
      setSaved(true);
      setSaveHint(typeof d.hint === "string" ? d.hint : null);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    "w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-base text-app-text placeholder-app-text-muted outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-app-accent focus:outline-none transition-colors duration-150";

  const hasFields = llm.base_url.trim() !== "" && llm.main_model.trim() !== "";

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="设置" />
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {loading && (
          <p className="flex items-center gap-2 text-ui-sm text-app-text-muted">
            <Loader2 size={14} className="animate-spin shrink-0" />
            正在加载…
          </p>
        )}
        {loadError && (
          <p className="flex items-center gap-2 text-ui-sm text-app-error">
            <AlertCircle size={14} className="shrink-0" />
            {loadError}
          </p>
        )}

        <p className="text-ui-sm text-app-text leading-relaxed">
        </p>

        <h3 className="text-ui-sm font-medium text-app-text mb-3 flex items-center gap-1.5">
          <Cpu size={14} className="text-app-accent" />
          Pipeline LLM
        </h3>
        <Field label="Base URL" icon={<Globe size={14} />}>
          <input className={inputClass} autoComplete="off" value={llm.base_url}
            onChange={(e) => { setLlm({ ...llm, base_url: e.target.value }); setTestStatus("idle"); setTestMessage(null); }} />
        </Field>
        <Field label="API Key" icon={<Key size={14} />}>
          <input className={inputClass} type="text" autoComplete="off"
            placeholder={llm.api_key_configured ? "已配置密钥（重新输入可覆盖）" : ""}
            value={apiKeyInput}
            onChange={(e) => { setApiKeyInput(e.target.value); setTestStatus("idle"); setTestMessage(null); }} />
        </Field>
        <Field label="模型名称" icon={<Cpu size={14} />}>
          <input className={inputClass} autoComplete="off" value={llm.main_model}
            onChange={(e) => { setLlm({ ...llm, main_model: e.target.value }); setTestStatus("idle"); setTestMessage(null); }} />
        </Field>

        {/* 主模型：测试 + 保存 */}
        <div className="flex gap-3 mt-3">
          <button type="button" disabled={!hasFields || testStatus === "testing"} onClick={() => void handleTest()}
            className="flex items-center gap-2 px-3 py-1.5 text-ui-sm rounded border border-app-border bg-app-bg-secondary hover:bg-app-bg disabled:opacity-40 disabled:cursor-not-allowed text-app-text transition-colors cursor-pointer">
            {testStatus === "testing" ? <Loader2 size={14} className="animate-spin" /> : testStatus === "ok" ? <CheckCircle2 size={14} className="text-green-500" /> : testStatus === "fail" ? <XCircle size={14} className="text-app-error" /> : <Zap size={14} />}
            {testStatus === "testing" ? "测试中…" : "测试连接"}
          </button>
          <button type="button" onClick={() => void handleSave()} disabled={saving || loading}
            className="flex items-center gap-2 px-4 py-2 bg-app-accent hover:bg-app-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-ui-base rounded transition-colors cursor-pointer">
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saving ? "保存中…" : saved ? "已保存" : "保存"}
          </button>
        </div>
        {testMessage && <div className={`text-ui-xs leading-relaxed px-2 py-1.5 rounded border ${testStatus === "ok" ? "border-green-500/30 bg-green-500/10 text-green-400" : "border-app-error/30 bg-app-error/10 text-app-error"}`}><span>{testMessage}</span>{testTime && <span className="ml-2 opacity-70">&mdash; {testStatus === "ok" ? "成功" : "失败"} {testTime}</span>}</div>}
        {saveError && <p className="flex items-center gap-2 text-ui-sm text-app-error"><AlertCircle size={14} className="shrink-0"/>{saveError}</p>}
        {saveHint && <p className="text-ui-xs text-app-text-muted leading-relaxed border border-app-border rounded px-2 py-1.5 bg-app-bg-secondary">{saveHint}</p>}

        <div className="border-t border-app-border/50 pt-4 mt-2">
          <h3 className="text-ui-sm font-medium text-app-text mb-3 flex items-center gap-1.5">
            <Zap size={14} className="text-app-accent" />
            HaGoKu Doctor（系统医生）
          </h3>
          <p className="text-ui-xs text-app-text-muted mb-3">独立 LLM。全部留空则复用主 LLM。填了任意一项则三项必须全填。</p>
          <Field label="Base URL" icon={<Globe size={14} />}>
            <input className={inputClass} autoComplete="off" value={metaUrl} onChange={(e) => setMetaUrl(e.target.value)} />
          </Field>
          <Field label="API Key" icon={<Key size={14} />}>
            <input className={inputClass} type="text" autoComplete="off"
              placeholder={llm.api_key_configured ? "已配置密钥（重新输入可覆盖）" : ""}
              value={metaKey} onChange={(e) => setMetaKey(e.target.value)} />
          </Field>
          <Field label="模型名称" icon={<Cpu size={14} />}>
            <input className={inputClass} autoComplete="off" value={metaModel} onChange={(e) => setMetaModel(e.target.value)} />
          </Field>
          <div className="flex gap-3 mt-3">
            <button type="button" disabled={testStatusMeta === "testing"} onClick={() => handleTestMeta()}
              className="flex items-center gap-2 px-3 py-1.5 text-ui-sm rounded border border-app-border bg-app-bg-secondary hover:bg-app-bg disabled:opacity-40 disabled:cursor-not-allowed text-app-text transition-colors cursor-pointer">
              {testStatusMeta === "testing" ? <Loader2 size={14} className="animate-spin" /> : testStatusMeta === "ok" ? <CheckCircle2 size={14} className="text-green-500" /> : testStatusMeta === "fail" ? <XCircle size={14} className="text-app-error" /> : <Zap size={14} />}
              {testStatusMeta === "testing" ? "测试中…" : "测试连接"}
            </button>
            <button type="button" onClick={() => void handleSaveMeta()} disabled={saving || loading}
              className="flex items-center gap-2 px-4 py-2 bg-app-accent hover:bg-app-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-ui-base rounded transition-colors cursor-pointer">
              {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
              {saving ? "保存中…" : saved ? "已保存" : "保存"}
            </button>
          </div>
          {testMessageMeta && <div className={`text-ui-xs leading-relaxed px-2 py-1.5 rounded border mt-2 ${testStatusMeta === "ok" ? "border-green-500/30 bg-green-500/10 text-green-400" : "border-app-error/30 bg-app-error/10 text-app-error"}`}><span>{testMessageMeta}</span>{testTimeMeta && <span className="ml-2 opacity-70">&mdash; {testStatusMeta === "ok" ? "成功" : "失败"} {testTimeMeta}</span>}</div>}
        </div>
      </div>
    </div>
  );
}