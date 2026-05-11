import { Server, Key, Database } from "lucide-react";
import { useState } from "react";
import { PanelHeader } from "../components/PanelHeader";
import { Field, Select } from "../components/FormField";

const LLM_PROVIDERS = ["openai", "anthropic", "local"] as const;

export default function SettingsPanel() {
  const [, setProvider] = useState<string>("openai");

  return (
    <div className="h-full flex flex-col bg-app-bg text-app-text max-md:min-h-[200px]">
      <PanelHeader title="Settings" />
      <div className="flex-1 overflow-auto p-4 space-y-4">
        <Field label="API Base URL" icon={<Server size={14} />}>
          <input
            className="w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-base text-app-text placeholder-app-text-muted outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-[#569cd6] focus:outline-none transition-colors"
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
            className="w-full bg-app-bg-secondary border border-app-border rounded px-2 py-1 text-ui-base text-app-text placeholder-app-text-muted outline-none focus:border-app-accent focus-visible:ring-1 focus-visible:ring-[#569cd6] focus:outline-none transition-colors"
            placeholder="./workspace"
            defaultValue="./workspace"
          />
        </Field>
      </div>
    </div>
  );
}