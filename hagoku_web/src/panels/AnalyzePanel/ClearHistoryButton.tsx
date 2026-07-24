import { useState } from "react";
import { Trash2 } from "lucide-react";

export function ClearHistoryButton({ currentProject, onClear }: { currentProject: string | null; onClear: () => void }) {
  const [showConfirm, setShowConfirm] = useState(false);
  if (!currentProject) return null;

  const handleClear = () => {
    setShowConfirm(false);
    // 先调 API 清除后端，再清前端状态
    // 不能反过来——onClear 里 cancel_analysis 会 save_state 写回 runs/
    fetch(`/api/projects/${currentProject}/clear-history`, { method: "POST" })
      .then(() => onClear())
      .catch(() => onClear());
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setShowConfirm(true)}
        className="flex items-center gap-1 px-2 py-0.5 border border-app-border rounded text-ui-xs normal-case tracking-normal font-medium text-app-text
          hover:border-app-error hover:text-app-error transition-colors cursor-pointer"
      >
        <Trash2 size={12} />
        清除历史
      </button>
      {showConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-app-bg border border-app-border rounded-lg p-6 max-w-sm mx-4 shadow-xl">
            <p className="text-ui-sm text-app-text mb-4">
              将清除该项目所有历史分析记录（运行记录、记忆）。数据文件保留。此操作不可撤销，确认清除？
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowConfirm(false)}
                className="px-4 py-1.5 border border-app-border rounded text-ui-sm text-app-text hover:bg-app-bg-secondary cursor-pointer">
                否
              </button>
              <button onClick={handleClear}
                className="px-4 py-1.5 bg-app-error text-white rounded text-ui-sm hover:bg-red-700 cursor-pointer">
                是，确认清除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
