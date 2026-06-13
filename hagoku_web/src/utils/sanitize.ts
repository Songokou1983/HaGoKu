import DOMPurify from "dompurify";

/** 清洗用户输入中的不可见字符（null bytes, 双向文本控制符等） */
export function sanitizeText(text: string): string {
  if (!text) return text;
  // 移除: null bytes, 所有控制字符 (0x00-0x1F 除 \t\n\r), Unicode 双向控制符
  return text
    .replace(/\x00/g, "")                     // null bytes
    .replace(/[\x01-\x08\x0B\x0C\x0E-\x1F]/g, "") // 控制字符（保留 \t\n\r）
    .replace(/[\u200B-\u200F\u2028-\u202F\uFEFF]/g, ""); // 零宽空格/双向控制/BOM
}

/**
 * 净化 HTML 字符串 — 移除 XSS 攻击向量（script/event handler 等），保留安全标签。
 * 用于 dangerouslySetInnerHTML 之前。
 */
export function sanitizeHtml(html: string): string {
  if (!html) return html;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "p", "br", "strong", "em", "b", "i", "u", "s", "code", "pre",
      "h1", "h2", "h3", "h4", "h5", "h6",
      "ul", "ol", "li", "a", "span", "div",
      "table", "thead", "tbody", "tr", "th", "td",
      "blockquote", "hr", "img",
    ],
    ALLOWED_ATTR: ["href", "src", "alt", "class", "id", "style", "target"],
  });
}

/** HTML 实体转义（用于纯文本插入到 HTML 中时防止注入） */
export function escapeHtml(text: string): string {
  if (!text) return text;
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
