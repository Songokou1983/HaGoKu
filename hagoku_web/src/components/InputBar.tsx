import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { Send, Zap, Loader2 } from "lucide-react";

export interface InputBarProps {
  placeholder?: string;
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function InputBar({
  placeholder = "Ask a question about your data...",
  onSend,
  disabled = false,
}: InputBarProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, onSend, disabled]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  const isDisabled = !value.trim() || disabled;

  return (
    <div className="border-t border-[#333] p-2 flex items-end gap-2">
      <Zap size={14} className="text-[#569cd6] shrink-0 mt-1.5" />
      <textarea
        ref={textareaRef}
        className="flex-1 bg-transparent border-none outline-none text-[13px] text-[#d4d4d4] placeholder-[#555] resize-none leading-relaxed max-h-[120px] focus-visible:ring-1 focus-visible:ring-[#569cd6] focus:outline-none"
        placeholder={placeholder}
        rows={1}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          autoResize();
        }}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      />
      <button
        onClick={handleSend}
        className="p-1 text-[#569cd6] hover:text-[#9cdcfe] disabled:text-[#444] shrink-0 transition-colors duration-150 active:scale-95"
        disabled={isDisabled}
        aria-label={disabled ? "Sending..." : "Send"}
      >
        {disabled ? (
          <Loader2 size={16} className="animate-spin" />
        ) : (
          <Send size={16} />
        )}
      </button>
    </div>
  );
}