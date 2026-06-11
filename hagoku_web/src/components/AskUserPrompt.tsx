import React from "react";

interface AskUserPromptProps {
  question: string;
  options?: string[];
  expected_format?: string;
  onReply: (answer: string) => void;
}

/** Phase C: 按 expected_format 分 3 种渲染：choice / free_text / yes_no */
const AskUserPrompt: React.FC<AskUserPromptProps> = ({
  question,
  options,
  expected_format,
  onReply,
}) => {
  const fmt = expected_format || "free_text";

  if (fmt === "yes_no") {
    return (
      <div className="ask-user-prompt yes-no">
        <p className="ask-question">{question}</p>
        <div className="ask-actions">
          <button onClick={() => onReply("是")} className="btn-yes">是</button>
          <button onClick={() => onReply("否")} className="btn-no">否</button>
        </div>
      </div>
    );
  }

  if (fmt === "choice" && options && options.length > 0) {
    return (
      <div className="ask-user-prompt choice">
        <p className="ask-question">{question}</p>
        <div className="ask-actions">
          {options.map((opt) => (
            <button key={opt} onClick={() => onReply(opt)}>{opt}</button>
          ))}
        </div>
      </div>
    );
  }

  // free_text (default)
  const [text, setText] = React.useState("");
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim()) {
      onReply(text.trim());
      setText("");
    }
  };

  return (
    <div className="ask-user-prompt free-text">
      <p className="ask-question">{question}</p>
      <form onSubmit={handleSubmit} className="ask-form">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="输入回复..."
          autoFocus
        />
        <button type="submit">发送</button>
      </form>
    </div>
  );
};

export default AskUserPrompt;
