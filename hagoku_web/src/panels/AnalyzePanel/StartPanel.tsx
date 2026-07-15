import { PlayCircle } from "lucide-react";
import { sanitizeText } from "../../utils/sanitize";

interface StartPanelProps {
  phase: string;
  currentProject: string | null;
  dataPath: string;
  canStart: boolean;
  queryText: string;
  setQueryText: (v: string) => void;
  handleStartSession: (sheetName?: string) => void;
}

export function StartPanel({
  phase, currentProject, dataPath, canStart,
  queryText, setQueryText, handleStartSession,
}: StartPanelProps) {
  if (phase !== "setup") return null;

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
      {!currentProject || !dataPath ? (
        <div className="text-center space-y-2">
          <div className="text-app-text-muted text-ui-sm">
            {!currentProject ? "请先选择一个项目" : "请选择或上传数据文件"}
          </div>
          <div className="text-app-text-muted text-ui-xs">准备好后点击"开始分析"</div>
        </div>
      ) : (
        <>
          <div className="text-center space-y-2">
            <div className="text-ui-sm text-app-text-muted">项目和数据文件已就绪</div>
            <div className="text-ui-xs text-app-text-muted opacity-60">
              需要暂停确认时会在对话区提示，并在下方出现输入框
            </div>
          </div>
          <div className="w-full max-w-md">
            <textarea
              value={queryText}
              onChange={(e) => setQueryText(sanitizeText(e.target.value))}
              placeholder="你想分析什么？例如：这批广告投放的 ROI 如何？哪个渠道转化最高？"
              rows={3}
              className="w-full px-3 py-2 bg-app-bg border border-app-border rounded-md text-ui-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:border-app-accent resize-none transition-colors"
            />
          </div>
        </>
      )}
      <button
        onClick={() => handleStartSession()}
        disabled={!canStart}
        className={`flex items-center gap-2 px-6 py-3 rounded-lg text-ui-base font-medium transition-all duration-200
          ${canStart
            ? "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer shadow-lg hover:shadow-app-accent/30 hover:-translate-y-0.5"
            : "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"}`}
      >
        <PlayCircle size={18} />
        开始分析
      </button>
    </div>
  );
}
