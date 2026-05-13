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

        <Field label="推理服务地址（Base URL）" icon={<Globe size={14} />}>
          <input
            className={inputClass}
            placeholder="http://localhost:8080/v1"
            autoComplete="off"
            value={llm.base_url}
            onChange={(e) => setLlm({ ...llm, base_url: e.target.value })}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted leading-relaxed">
            OpenAI 兼容接口地址，需包含 <span className="font-mono">/v1</span> 后缀。勿填 HaGoKu 本服务端口（默认
            8000）。
          </p>
        </Field>

        <Field label="API Key" icon={<Key size={14} />}>
          <input
            className={inputClass}
            type="password"
            placeholder={llm.api_key_configured ? "已保存 · 留空则不修改" : "本地模型可填 none"}
            autoComplete="new-password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
          />
          <p className="mt-1 text-ui-xs text-app-text-muted leading-relaxed">
            与上面地址同属一个推理服务，只填一份 Key。
          </p>
        </Field>

        <div className="rounded border border-app-border bg-app-bg-secondary/30 px-3 py-2.5 space-y-3">
          <p className="text-ui-xs text-app-text-muted leading-relaxed">
            <span className="text-app-text font-medium">双层模型</span>：快速步（Scout / Cleaner / Reporter）与深度步（Analyst）可用不同模型名，以平衡速度/成本与推理质量。
            下面三项是<strong className="text-app-text">三个模型名</strong>；后两项留空时，会自动与「默认模型」相同。
          </p>

          <Field label="默认模型（必填）" icon={<Cpu size={14} />}>
            <input
              className={inputClass}
              placeholder="例如 Qwen2.5-7B-Instruct"
              autoComplete="off"
              value={llm.model}
              onChange={(e) => setLlm({ ...llm, model: e.target.value })}
            />
            <p className="mt-1 text-ui-xs text-app-text-muted">对应环境变量 HAGOKYU_LLM_MODEL；后两格不填时全流程都用它。</p>
          </Field>

          <Field label="快速模型（选填）" icon={<Zap size={14} />}>
            <input
              className={inputClass}
              placeholder="留空 = 与默认模型相同"
              autoComplete="off"
              value={llm.model_quick}
              onChange={(e) => setLlm({ ...llm, model_quick: e.target.value })}
            />
            <p className="mt-1 text-ui-xs text-app-text-muted">HAGOKYU_LLM_MODEL_QUICK；用于 Scout、Cleaner、Reporter。</p>
          </Field>

          <Field label="深度模型（选填）" icon={<BrainCircuit size={14} />}>
            <input
              className={inputClass}
              placeholder="留空 = 与默认模型相同"
              autoComplete="off"
              value={llm.model_deep}
              onChange={(e) => setLlm({ ...llm, model_deep: e.target.value })}
            />
            <p className="mt-1 text-ui-xs text-app-text-muted">HAGOKYU_LLM_MODEL_DEEP；用于 Analyst。</p>
          </Field>
        </div>

        <Field label="项目数据目录（只读）" icon={<FolderOpen size={14} />}>
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
          {saving ? "保存中…" : saved ? "已保存" : "保存 LLM 设置"}
        </button>
      </div>
    </div>
  );
}
