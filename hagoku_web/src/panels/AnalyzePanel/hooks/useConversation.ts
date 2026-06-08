import { useState } from "react";
import type { ConvoMessage } from "../types";
import { uid } from "../utils";

export function useConversation() {
  const [messages, setMessages] = useState<ConvoMessage[]>([]);

  const addSystemMsg = (text: string, timestamp?: string) => {
    const ts = timestamp ?? new Date().toISOString();
    setMessages((prev) => [...prev, { id: uid(), role: "system", text, timestamp: ts }]);
  };

  const addUserMsg = (text: string) => {
    const ts = new Date().toISOString();
    setMessages((prev) => [...prev, { id: uid(), role: "user", text, timestamp: ts }]);
  };

  const addAgentMsg = (text: string, html?: string, timestamp?: string) => {
    const ts = timestamp ?? new Date().toISOString();
    const msg: ConvoMessage = { id: uid(), role: "agent", text, timestamp: ts };
    if (html) (msg as any).html = html;
    setMessages((prev) => [...prev, msg]);
  };

  const addWorkflowCard = (card: Partial<ConvoMessage> & { id?: string }) => {
    const id = card.id ?? uid();
    const ts = card.timestamp ?? new Date().toISOString();
    setMessages((prev) => [...prev, {
      id, role: "workflow", text: card.text ?? "", timestamp: ts,
      fieldReview: card.fieldReview,
      cleaningReview: card.cleaningReview,
      analystReview: card.analystReview,
    }]);
  };

  const updateWorkflowCard = (id: string, updates: Partial<ConvoMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    );
  };

  const clearMessages = () => setMessages([]);

  return {
    messages, setMessages,
    addSystemMsg, addUserMsg, addAgentMsg, addWorkflowCard, updateWorkflowCard,
    clearMessages,
  };
}
