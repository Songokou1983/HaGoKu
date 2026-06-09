/** 清洗用户输入中的不可见字符（null bytes, 双向文本控制符等） */
export function sanitizeText(text: string): string {
  if (!text) return text;
  // 移除: null bytes, 所有控制字符 (0x00-0x1F 除 \t\n\r), Unicode 双向控制符
  return text
    .replace(/\x00/g, "")                     // null bytes
    .replace(/[\x01-\x08\x0B\x0C\x0E-\x1F]/g, "") // 控制字符（保留 \t\n\r）
    .replace(/[\u200B-\u200F\u2028-\u202F\uFEFF]/g, ""); // 零宽空格/双向控制/BOM
}
