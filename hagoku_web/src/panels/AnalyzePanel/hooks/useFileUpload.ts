import { useState, useCallback, useEffect, useRef } from "react";
import type { ProjectFile } from "../types";

export function useFileUpload(
  currentProject: string | null,
  dataPath: string,
  setDataPath: (v: string) => void,
) {
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [showFileDropdown, setShowFileDropdown] = useState(false);
  const [showProjectDropdown, setShowProjectDropdown] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileExists, setFileExists] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const projectDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node))
        setShowFileDropdown(false);
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node))
        setShowProjectDropdown(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const loadFiles = useCallback((proj: string, signal?: AbortSignal) => {
    setFilesLoading(true);
    fetch(`/api/projects/${proj}/files`, { signal })
      .then((r) => r.json())
      .then((d: { files: ProjectFile[] }) => setProjectFiles(d.files ?? []))
      .catch((e) => { if ((e as Error).name !== 'AbortError') setProjectFiles([]); })
      .finally(() => setFilesLoading(false));
  }, []);

  useEffect(() => {
    if (!currentProject) { setDataPath(""); setProjectFiles([]); return; }
    const abort = new AbortController();
    loadFiles(currentProject, abort.signal);
    fetch(`/api/projects/${currentProject}/detail`, { signal: abort.signal })
      .then((r) => r.json())
      .then((d: { data_path?: string; last_query?: string }) => {
        if (d.data_path) setDataPath(d.data_path);
      })
      .catch((e) => { if ((e as Error).name !== 'AbortError') { /* ignore */ } });
    return () => abort.abort();
  }, [currentProject, loadFiles]);

  useEffect(() => {
    if (!currentProject || !dataPath) { setFileExists(false); return; }
    const abort = new AbortController();
    fetch(`/api/projects/${currentProject}/files`, { signal: abort.signal })
      .then(r => r.json())
      .then((d: { files?: Array<{path: string}> }) => {
        setFileExists((d.files || []).some((f: {path: string}) => f.path === dataPath));
      })
      .catch((e) => { if ((e as Error).name !== 'AbortError') setFileExists(false); });
    return () => abort.abort();
  }, [currentProject, dataPath]);

  const handleUpload = useCallback(async (file: File) => {
    if (!currentProject) return;
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/projects/${currentProject}/upload`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "上传失败" }));
        throw new Error(err.detail ?? "上传失败");
      }
      const data = await res.json() as { path: string };
      setDataPath(data.path);
      loadFiles(currentProject);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [currentProject, loadFiles]);

  return {
    projectFiles, filesLoading, showFileDropdown, setShowFileDropdown,
    showProjectDropdown, setShowProjectDropdown, uploading, uploadError,
    setUploadError, fileExists, fileInputRef, dropdownRef, projectDropdownRef,
    loadFiles, handleUpload,
  };
}
