import { Server, Key, Database, Save, CheckCircle2 } from "lucide-react";
import { useState, useEffect } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { Field, Select } from "../components/FormField";

const STORAGE_KEY = "hagoku_settings";

interface Settings {
  baseUrl: string;
  model: string;
  workspace: string;
}

const defaults: Settings = { baseUrl: "http://localhost:8000", model: "", workspace: "" };

const LLM_PROVIDERS = ["openai", "anthropic", "local"] as const;

export default function SettingsPanel() {
  const [cfg, setCfg] = useState<Settings>(() => {
    try { return { ...defaults, ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") }; }
    catch { return defaults; }
  });
  const [saved, setSaved] = useState(false);

  // Mount 时从 /api/config 合并服务端默认值
  useEffect(() => {
    let cancelled = false;
    fetch("/api/config").then((r) => r.json()).then((d) => {
      if (!cancelled) {
        setCfg((prev) => ({
          baseUrl: prev.baseUrl || d.base_url || defaults.baseUrl,
          model: prev.model || d.model || "",
          workspace: prev.workspace || d.workspace || "",
        }));
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const handleSave = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Settings" />
      <div className="flex-1 overflow-auto p-4 space-y-4">
        <Field label="接口地址" icon={<Server size={14} />}>
          <input
            className="w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-base text-app-text placeholder-app-text-muted outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-app-accent focus:outline-none transition-colors duration-150"
            placeholder="http://localhost:8000"
            value={cfg.baseUrl}
            onChange={(e) => setCfg({ ...cfg, baseUrl: e.target.value })}
          />
        </Field>

        <Field label="模型提供商" icon={<Key size={14} />}>
          <Select
            options={[...LLM_PROVIDERS]}
            value={cfg.model}
            onChange={(v) => setCfg({ ...cfg, model: v })}
          />
        </Field>

        <Field label="工作目录" icon={<Database size={14} />}>
          <input
            className="w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-base text-app-text placeholder-app-text-muted outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-app-accent focus:outline-none transition-colors duration-150"
            placeholder="./workspace"
            value={cfg.workspace}
            onChange={(e) => setCfg({ ...cfg, workspace: e.target.value })}
          />
        </Field>

        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-4 py-2 bg-app-accent hover:bg-app-accent-hover
                     text-white text-ui-base rounded transition-colors duration-150 cursor-pointer"
        >
          {saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
          {saved ? "已保存" : "保存设置"}
        </button>
      </div>
    </div>
  );
}