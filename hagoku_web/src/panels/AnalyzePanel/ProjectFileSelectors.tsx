import { Loader2, FolderOpen, ChevronDown, FileText, Upload, X, CheckCircle2 } from "lucide-react";
import type { ProjectFile } from "./types";
import { fmtSize } from "./utils";

interface ProjectFileSelectorsProps {
  currentProject: string | null;
  projects: string[];
  setCurrentProject: (p: string) => void;
  setActiveView: (v: any) => void;
  dataPath: string;
  setDataPath: (p: string) => void;
  selectedFileName: string | null;
  projectFiles: ProjectFile[];
  filesLoading: boolean;
  showFileDropdown: boolean;
  setShowFileDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  showProjectDropdown: boolean;
  setShowProjectDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  uploading: boolean;
  uploadError: string | null;
  setUploadError: (v: string | null) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  dropdownRef: React.RefObject<HTMLDivElement | null>;
  projectDropdownRef: React.RefObject<HTMLDivElement | null>;
  handleUpload: (f: File) => Promise<void>;
  phase: string;
}

export function ProjectFileSelectors(props: ProjectFileSelectorsProps) {
  const {
    currentProject, projects, setCurrentProject, setActiveView,
    dataPath, setDataPath, selectedFileName,
    projectFiles, filesLoading, showFileDropdown, setShowFileDropdown,
    showProjectDropdown, setShowProjectDropdown,
    uploading, uploadError, setUploadError,
    fileInputRef, dropdownRef, projectDropdownRef, handleUpload, phase,
  } = props;

  return (
    <div className="px-3 py-2 border-b border-app-border bg-app-bg-secondary shrink-0 space-y-2">
      {/* Project selector */}
      <div className="flex items-center gap-2">
        <span className="text-ui-xs text-app-text-muted w-12 shrink-0">项目</span>
        <div className="relative flex-1" ref={projectDropdownRef}>
          <button
            onClick={() => setShowProjectDropdown((v) => !v)}
            disabled={phase === "running"}
            className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded
                       text-ui-sm transition-colors
                       ${phase !== "running"
                         ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                         : "border-app-border opacity-50 cursor-not-allowed text-app-text-muted"}`}
          >
            <FolderOpen size={13} className="text-app-accent shrink-0" />
            <span className="flex-1 text-left truncate font-mono">{currentProject ?? "— 选择项目 —"}</span>
            <ChevronDown size={12} className="text-app-text-muted shrink-0" />
          </button>
          {showProjectDropdown && (
            <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-48 overflow-y-auto">
              {projects.length === 0
                ? <div className="px-3 py-2 text-ui-xs text-app-text-muted">暂无项目</div>
                : projects.map((p) => (
                  <button key={p} onClick={() => { setCurrentProject(p); setShowProjectDropdown(false); }}
                    className={`w-full text-left px-3 py-1.5 text-ui-sm font-mono hover:bg-app-bg cursor-pointer
                      ${p === currentProject ? "text-app-accent" : "text-app-text"}`}>
                    {p === currentProject && <CheckCircle2 size={11} className="inline mr-1.5 text-app-accent" />}
                    {p}
                  </button>
                ))}
              <div className="border-t border-app-border">
                <button onClick={() => { setShowProjectDropdown(false); setActiveView("projects"); }}
                  className="w-full text-left px-3 py-1.5 text-ui-xs text-app-accent hover:bg-app-bg cursor-pointer">
                  + 新建项目 →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* File selector */}
      <div className="flex items-center gap-2">
        <span className="text-ui-xs text-app-text-muted w-12 shrink-0">数据</span>
        <div className="relative flex-1" ref={dropdownRef}>
          <button
            disabled={!currentProject || phase === "running"}
            onClick={() => setShowFileDropdown((v) => !v)}
            className={`w-full flex items-center gap-2 px-2 py-1.5 bg-app-bg border rounded text-ui-sm transition-colors
              ${currentProject && phase !== "running"
                ? "border-app-border hover:border-app-accent cursor-pointer text-app-text"
                : "border-app-border opacity-40 cursor-not-allowed text-app-text-muted"}`}
          >
            <FileText size={13} className={selectedFileName ? "text-app-accent shrink-0" : "text-app-text-muted shrink-0"} />
            <span className="flex-1 text-left truncate font-mono text-ui-xs">{selectedFileName ?? "— 选择文件 —"}</span>
            {filesLoading
              ? <Loader2 size={12} className="animate-spin text-app-text-muted shrink-0" />
              : <ChevronDown size={12} className="text-app-text-muted shrink-0" />}
          </button>
          {showFileDropdown && currentProject && (
            <div className="absolute left-0 right-0 top-full mt-1 z-30 bg-app-bg-secondary border border-app-border rounded shadow-lg max-h-56 overflow-y-auto">
              {projectFiles.length === 0
                ? <div className="px-3 py-3 text-ui-xs text-app-text-muted text-center">暂无数据文件，请上传</div>
                : projectFiles.map((f) => (
                  <button key={f.path} onClick={() => { setDataPath(f.path); setShowFileDropdown(false); }}
                    className={`w-full text-left px-3 py-2 hover:bg-app-bg cursor-pointer border-b border-app-border/50 last:border-0
                      ${f.path === dataPath ? "text-app-accent" : "text-app-text"}`}>
                    <div className="flex items-center gap-2">
                      {f.path === dataPath && <CheckCircle2 size={11} className="text-app-accent shrink-0" />}
                      <span className="text-ui-xs font-mono truncate flex-1">{f.name}</span>
                      <span className="text-ui-xs text-app-text-muted shrink-0">{fmtSize(f.size)}</span>
                    </div>
                  </button>
                ))}
            </div>
          )}
        </div>
        {/* Upload button */}
        <div className="relative shrink-0">
          <input ref={fileInputRef} type="file"
            accept=".csv,.tsv,.json,.jsonl,.xlsx,.xls,.parquet,.txt"
            className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
            disabled={!currentProject || uploading || phase === "running"}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleUpload(f); }}
          />
          <button disabled={!currentProject || uploading || phase === "running"}
            className={`flex items-center gap-1 px-2 py-1.5 border rounded text-ui-xs transition-colors
              ${currentProject && !uploading && phase !== "running"
                ? "border-app-accent text-app-accent hover:bg-app-accent hover:text-white cursor-pointer"
                : "border-app-border text-app-text-muted opacity-40 cursor-not-allowed"}`}>
            {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            {uploading ? "上传中…" : "上传"}
          </button>
        </div>
      </div>
      {uploadError && (
        <div className="flex items-center gap-1 text-ui-xs text-app-error">
          <X size={11} />{uploadError}
          <button onClick={() => setUploadError(null)} className="ml-auto text-app-text-muted hover:text-app-text cursor-pointer">忽略</button>
        </div>
      )}
    </div>
  );
}
