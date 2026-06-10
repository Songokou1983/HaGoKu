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

/** localStorage：用户是否展开过「高级设置」；与本机已配置 QUICK≠主 时强制展开无关 */
const ADVANCED_LLM_STORAGE_KEY = "hagoku_settings_advanced_llm_open";

function normalizeLlmFromApi(raw: Record<string, unknown>): LlmConfigPayload {
  const base_url = typeof raw.base_url === "string" ? raw.base_url : "";
  const api_key_configured = typeof raw.api_key_configured === "boolean" ? raw.api_key_configured : false;
  let main_model = typeof raw.main_model === "string" ? raw.main_model : "";
  let sub_model = typeof raw.sub_model === "string" ? raw.sub_model : "";
  if (!main_model) {
    const m = typeof raw.model === "string" ? raw.model : "";
    const md = typeof raw.model_deep === "string" ? raw.model_deep : "";
    main_model = (m || md).trim();
  }
  if (!sub_model && typeof raw.model_quick === "string" && raw.model_quick.trim() && raw.model_quick.trim() !== main_model) {
    sub_model = raw.model_quick.trim();
  }
  return { base_url, main_model, sub_model, api_key_configured };
}

function formFromNormalized(n: LlmConfigPayload): LlmFormState {
  return {
    base_url: n.base_url,
    main_model: n.main_model,
    api_key_configured: n.api_key_configured,
  };
}

function hadDistinctQuickName(n: LlmConfigPayload): boolean {
  const s = n.sub_model.trim();
  return Boolean(s && s !== n.main_model.trim());
}

export default function SettingsPanel() {
  const [llm, setLlm] = useState<LlmFormState>(emptyLlm);

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
          setLlm(formFromNormalized(n));
          const distinct = hadDistinctQuickName(n);
          if (distinct) {
            setAdvancedLlmOpen(true);
            setSubModelQuick(n.sub_model.trim());
          } else {
            setSubModelQuick("");
            try {
              setAdvancedLlmOpen(localStorage.getItem(ADVANCED_LLM_STORAGE_KEY) === "1");
            } catch {
              setAdvancedLlmOpen(false);
            }
          }
        } else {
          setLlm(emptyLlm);
          setSubModelQuick("");
          try {
            setAdvancedLlmOpen(localStorage.getItem(ADVANCED_LLM_STORAGE_KEY) === "1");
          } catch {
            setAdvancedLlmOpen(false);
          }
        }
        setApiKeyInput("");
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
          main_model: llm.main_model.trim(),
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
        const distinct = hadDistinctQuickName(n);
        if (distinct) {
          setAdvancedLlmOpen(true);
          setSubModelQuick(n.sub_model.trim());
        } else {
          setSubModelQuick("");
        }
      }
      setApiKeyInput("");
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
          这里只管「大模型在哪、叫什么、密钥多少」。不要填本分析页的端口，也不要填 HaGoKu Studio 后端默认的 8000。
        </p>

        <Field label="大模型服务网址" icon={<Globe size={14} />}>
          <input
            className={inputClass}
            placeholder="例：http://127.0.0.1:8080/v1"
            autoComplete="off"
            value={llm.base_url}
            onChange={(e) => {
              setLlm({ ...llm, base_url: e.target.value });
              setTestStatus("idle");
              setTestMessage(null);
            }}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">从你自己部署的推理软件说明里抄，一般末尾带 /v1。</p>
        </Field>

        <Field label="密钥" icon={<Key size={14} />}>
          <input
            className={inputClass}
            type="text"
            placeholder="粘贴 API 密钥"
            value={apiKeyInput}
            onChange={(e) => {
              setApiKeyInput(e.target.value);
              setTestStatus("idle");
              setTestMessage(null);
            }}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">和上面网址是同一套服务，只填一个密钥。</p>
        </Field>

        <Field label="模型名称" icon={<Cpu size={14} />}>
          <input
            className={inputClass}
            placeholder="在推理服务里注册的名字，例如 Qwen2.5-32B-Instruct"
            autoComplete="off"
            value={llm.main_model}
            onChange={(e) => {
              setLlm({ ...llm, main_model: e.target.value });
              setTestStatus("idle");
              setTestMessage(null);
            }}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">必填。全流程用同一个在推理服务里注册的名字。</p>
        </Field>

        {/* 测试连接 */}
        <button
          type="button"
          disabled={!hasFields || testStatus === "testing"}
          onClick={() => void handleTest()}
          className="flex items-center gap-2 px-3 py-1.5 text-ui-sm rounded border border-app-border
                     bg-app-bg-secondary hover:bg-app-bg disabled:opacity-40 disabled:cursor-not-allowed
                     text-app-text transition-colors duration-150 cursor-pointer"
        >
          {testStatus === "testing" ? (
            <Loader2 size={14} className="animate-spin shrink-0" />
          ) : testStatus === "ok" ? (
            <CheckCircle2 size={14} className="text-green-500 shrink-0" />
          ) : testStatus === "fail" ? (
            <XCircle size={14} className="text-app-error shrink-0" />
          ) : (
            <Zap size={14} className="shrink-0" />
          )}
          {testStatus === "testing" ? "测试中…" : "测试模型连接"}
        </button>
        {testMessage && (
          <div
            className={`text-ui-xs leading-relaxed px-2 py-1.5 rounded border ${
              testStatus === "ok"
                ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400"
                : "border-app-error/30 bg-app-error/10 text-app-error"
            }`}
          >
            <span>{testMessage}</span>
            {testTime && (
              <span className="ml-2 opacity-70">
                &mdash; {testStatus === "ok" ? "成功" : "失败"} {testTime}
              </span>
            )}
          </div>
        )}

        {saveError && (
          <p className="flex items-center gap-2 text-ui-sm text-app-error">
            <AlertCircle size={14} className="shrink-0" />
            {saveError}
          </p>
        )}
        {saveHint && (
          <p className="text-ui-xs text-app-text-muted leading-relaxed border border-app-border rounded px-2 py-1.5 bg-app-bg-secondary">
            {saveHint}
          </p>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            onClick={async () => {
              try {
                const r = await fetch("/api/analysis/cancel", { method: "POST" });
                const d = await r.json();
                setSaveHint(d.message || "已请求终止");
              } catch {
                setSaveHint("终止请求失败");
              }
            }}
            className="flex items-center gap-2 px-4 py-2 bg-app-error/20 hover:bg-app-error/30
                       text-app-error text-ui-base rounded border border-app-error/40
                       transition-colors duration-150 cursor-pointer"
          >
            强制终止当前分析
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving || loading}
            className="flex items-center gap-2 px-4 py-2 bg-app-accent hover:bg-app-accent-hover disabled:opacity-50 disabled:cursor-not-allowed
                       text-white text-ui-base rounded transition-colors duration-150 cursor-pointer"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saving ? "保存中…" : saved ? "已保存" : "保存设置"}
          </button>
        </div>
      </div>
    </div>
  );
}