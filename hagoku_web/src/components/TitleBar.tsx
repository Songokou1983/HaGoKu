import { useState, useEffect } from "react";
import { Minus, Square, X } from "lucide-react";

declare global {
  interface Window {
    hagokuDesktop?: {
      minimize: () => void;
      maximize: () => void;
      close: () => void;
      isMaximized: () => Promise<boolean>;
      onStateChanged: (cb: (maximized: boolean) => void) => void;
    };
  }
}

export function TitleBar() {
  const [maximized, setMaximized] = useState(false);
  const api = window.hagokuDesktop;

  useEffect(() => {
    if (!api) return;
    api.isMaximized().then(setMaximized);
    api.onStateChanged(setMaximized);
  }, [api]);

  if (!api) return null; // not in Electron — hide

  return (
    <div
      className="h-9 flex items-center justify-between shrink-0 select-none"
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
    >
      <span className="text-ui-xs text-app-text-muted pl-3 font-mono tracking-wide">
        HaGoKu Studio
      </span>
      <div className="flex h-full" style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}>
        <button onClick={api.minimize} className="w-10 h-full flex items-center justify-center text-app-text-muted hover:bg-app-bg-tertiary transition-colors cursor-pointer" aria-label="最小化">
          <Minus size={13} />
        </button>
        <button onClick={api.maximize} className="w-10 h-full flex items-center justify-center text-app-text-muted hover:bg-app-bg-tertiary transition-colors cursor-pointer" aria-label={maximized ? "还原" : "最大化"}>
          <Square size={11} />
        </button>
        <button onClick={api.close} className="w-10 h-full flex items-center justify-center text-app-text-muted hover:bg-red-600 hover:text-white transition-colors cursor-pointer" aria-label="关闭">
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
