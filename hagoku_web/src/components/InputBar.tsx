import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";

import { sanitizeText } from "../utils/sanitize";

export interface InputBarProps {
  /** Placeholder text */
  placeholder?: string;
  /** Send callback */
  onSend: (text: string) => void;
  /** Controlled value (optional) */
  value?: string;
  /** Controlled onChange (optional) */
  onChange?: (value: string) => void;
  /** Disabled state */
  disabled?: boolean;
  /** Footer hint shown below the input */
  footerHint?: string;
  /** External ref for focusing */
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
  /** Show send button with label */
  sendLabel?: string;
  /** Log function (WS __log channel) */
  log?: (msg: string) => void;
}

export function InputBar({
  placeholder = "输入回复后 Enter 发送",
  onSend,
  value: controlledValue,
  onChange: controlledOnChange,
  disabled = false,
  footerHint,
  inputRef: externalRef,
  sendLabel,
  log,
}: InputBarProps) {
  const internalRef = useRef<HTMLTextAreaElement>(null);
  const [internalValue, setInternalValue] = useState("");
  const textareaRef = externalRef || internalRef;

  const isControlled = controlledValue !== undefined;
  const value = isControlled ? (controlledValue ?? "") : internalValue;

  const setValue = (v: string) => {
    const sanitized = sanitizeText(v);
    if (isControlled) {
      controlledOnChange?.(sanitized);
    } else {
      setInternalValue(sanitized);
    }
  };

  const handleSend = useCallback(() => {
    const text = sanitizeText(value).trim();
    if (!text || disabled) {
      log?.(`[InputBar] handleSend blocked: textEmpty=${!text} disabled=${disabled} value.length=${value?.length ?? 0}`);
      return;
    }
    log?.(`[InputBar] handleSend → onSend text="${text.slice(0, 40)}"`);
    onSend(text);
    if (!isControlled) setInternalValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, onSend, disabled, isControlled]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      const composing = e.nativeEvent.isComposing;
      const keyCode229 = (e.nativeEvent as any).keyCode === 229;
      if (composing || keyCode229) {
        log?.(`[InputBar] keyDown Enter blocked: isComposing=${composing} keyCode229=${keyCode229}`);
        return;
      }
      e.preventDefault();
      log?.(`[InputBar] keyDown Enter → handleSend value.length=${value?.length ?? 0} disabled=${disabled}`);
      handleSend();
    },
    [handleSend, value, disabled],
  );

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  const isDisabled = !value.trim() || disabled;

  return (
    <div>
      <div className="p-2 flex items-end gap-2">
        <textarea
          ref={textareaRef}
          aria-label="输入"
          className="flex-1 bg-app-bg-secondary border rounded px-3 py-2
            text-ui-sm text-app-text placeholder-app-text-muted resize-none
            focus:outline-none transition-colors
            border-app-accent/50 focus:border-app-accent
            leading-relaxed max-h-[120px]"
          placeholder={placeholder}
          rows={2}
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
          className={`px-4 py-2 rounded text-ui-sm font-medium transition-colors shrink-0 flex items-center gap-1.5
            ${
              isDisabled
                ? "bg-app-bg-secondary border border-app-border text-app-text-muted cursor-not-allowed"
                : "bg-app-accent hover:bg-app-accent-hover text-white cursor-pointer"
            }`}
          disabled={isDisabled}
          aria-label={disabled ? "发送中…" : "发送"}
        >
          {disabled && !sendLabel ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Send size={14} />
          )}
          {sendLabel || null}
        </button>
      </div>
      {footerHint && (
        <div className="px-2 pb-1 text-ui-xs text-app-text-muted">
          {footerHint}
        </div>
      )}
    </div>
  );
}
