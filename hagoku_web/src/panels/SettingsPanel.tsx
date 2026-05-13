import { useState, useEffect, useCallback } from "react";
import {
  Globe,
  Cpu,
  Key,
  FolderOpen,
  Save,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Zap,
  BrainCircuit,
} from "lucide-react";
import { PanelHeader } from "../components/PanelHeader";
import { Field } from "../components/FormField";

/** 与 GET /api/config 对齐 */
interface LlmConfigPayload {
  base_url: string;
  model: string;
  model_quick: string;
  model_deep: string;
  api_key_configured: boolean;
}

interface ConfigResponse {
  llm: LlmConfigPayload;
  projects_root: string;
}

const emptyLlm: LlmConfigPayload = {
  base_url: "",
  model: "",
  model_quick: "",
  model_deep: "",
  api_key_configured: false,
};

export default function SettingsPanel() {
  const [llm, setLlm] = useState<LlmConfigPayload>(emptyLlm);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [projectsRoot, setProjectsRoot] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadConfig = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    fetch("/api/config")
      .then(async (r) => {
        if (!r.ok) throw new Error(`加载失败 (${r.status})`);
        return r.json() as Promise<ConfigResponse>;
      })
      .then((d) => {
        setLlm(d.llm ?? emptyLlm);
        setProjectsRoot(d.projects_root ?? "");
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
          model: llm.model.trim(),
          api_key: apiKeyInput.trim(),
          model_quick: llm.model_quick.trim(),
          model_deep: llm.model_deep.trim(),
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
      if (d.llm) setLlm(d.llm);
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
          这里只管「大模型在哪、叫什么、密钥多少」。不要填本分析页的端口，也不要填 HaGoKu 后端默认的 8000。
        </p>

        <Field label="大模型服务网址" icon={<Globe size={14} />}>
          <input
            className={inputClass}
            placeholder="例：http://127.0.0.1:8080/v1"
            autoComplete="off"
            value={llm.base_url}
            onChange={(e) => setLlm({ ...llm, base_url: e.target.value })}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">从你自己部署的推理软件说明里抄，一般末尾带 /v1。</p>
        </Field>

        <Field label="密钥" icon={<Key size={14} />}>
          <input
            className={inputClass}
            type="password"
            placeholder={llm.api_key_configured ? "已保存过，不想改就空着" : "本地没密钥就填 none"}
            autoComplete="new-password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">和上面网址是同一套服务，只填一个密钥。</p>
        </Field>

        <Field label="主用模型名字" icon={<Cpu size={14} />}>
          <input
            className={inputClass}
            placeholder="在推理服务里注册的名字，例如 Qwen2.5-7B-Instruct"
            autoComplete="off"
            value={llm.model}
            onChange={(e) => setLlm({ ...llm, model: e.target.value })}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">必填。下面两格不配时，全程都用这个名字。</p>
        </Field>

        <Field label="前面步骤用的模型名（可不配）" icon={<Zap size={14} />}>
          <input
            className={inputClass}
            placeholder="不配就和主用模型一样；要配就写另一个名字"
            autoComplete="off"
            value={llm.model_quick}
            onChange={(e) => setLlm({ ...llm, model_quick: e.target.value })}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">看表、洗数据、写报告那几步。一般和主用模型填同一个就行。</p>
        </Field>

        <Field label="后面统计用的模型名（可不配）" icon={<BrainCircuit size={14} />}>
          <input
            className={inputClass}
            placeholder="不配就和主用模型一样；想更准可以换更大的模型名"
            autoComplete="off"
            value={llm.model_deep}
            onChange={(e) => setLlm({ ...llm, model_deep: e.target.value })}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted">只做假设检验、回归那块。不配也和主用模型一样。</p>
        </Field>

        <Field label="项目数据放在哪（只读）" icon={<FolderOpen size={14} />}>
          <input className={`${inputClass} opacity-80 cursor-not-allowed`} readOnly value={projectsRoot} />
        </Field>

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
  );
}
