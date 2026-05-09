import { Server, Key, Database } from "lucide-react";
import { useState } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { Field, Select } from "../components/FormField";

const LLM_PROVIDERS = ["openai", "anthropic", "local"] as const;

export default function SettingsPanel() {
  const [, setProvider] = useState<string>("openai");

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e] text-[#cccccc]">
      <PanelHeader title="Settings" />
      <div className="flex-1 overflow-auto p-4 space-y-4">
        <Field label="API Base URL" icon={<Server size={14} />}>
          <input
            className="w-full bg-[#252525] border border-[#444] rounded px-2 py-1 text-[13px] text-[#d4d4d4] placeholder-[#555] outline-none focus:border-[#569cd6] transition-colors"
            placeholder="http://localhost:8000"
            defaultValue="http://localhost:8000"
          />
        </Field>

        <Field label="LLM Provider" icon={<Key size={14} />}>
          <Select
            options={[...LLM_PROVIDERS]}
            value="openai"
            onChange={setProvider}
          />
        </Field>

        <Field label="Workspace Dir" icon={<Database size={14} />}>
          <input
            className="w-full bg-[#252525] border border-[#444] rounded px-2 py-1 text-[13px] text-[#d4d4d4] placeholder-[#555] outline-none focus:border-[#569cd6] transition-colors"
            placeholder="./workspace"
            defaultValue="./workspace"
          />
        </Field>
      </div>
    </div>
  );
}