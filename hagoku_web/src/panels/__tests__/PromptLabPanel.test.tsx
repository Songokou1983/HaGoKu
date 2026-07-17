import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import PromptLabPanel from "../PromptLabPanel";

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function mockFetchResponse(data: any, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(data),
  } as Response);
}

describe("PromptLabPanel", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    // Default: return empty dumps + current prompt (for useEffect on mount)
    mockFetch.mockImplementation((url: string) => {
      if (url.includes("/run")) {
        return mockFetchResponse({
          ok: true,
          content: "分析结果",
          tokens: 42,
          model: "test-model",
          tool_calls: [{ name: "get_stats", arguments: '{"col":"x"}' }],
        });
      }
      return mockFetchResponse({ ok: true });
    });
  });

  it("renders the panel title", async () => {
    render(<PromptLabPanel />);
    expect(await screen.findByText("Prompt Lab")).toBeDefined();
  });

  it("renders no emoji icons (uses Lucide only)", async () => {
    render(<PromptLabPanel />);
    await screen.findByText("Prompt Lab");
    const html = document.body.innerHTML;
    // No emoji characters
    expect(html).not.toContain("❌");
    expect(html).not.toContain("▶");
    expect(html).not.toContain("📋");
    expect(html).not.toContain("💾");
    expect(html).not.toContain("🔍");
  });

  it("shows dirty badge when prompt is modified", async () => {
    render(<PromptLabPanel />);
    await screen.findByText("Prompt Lab");

    // Should not show dirty badge initially
    expect(screen.queryByText("已修改")).toBeNull();

    // Find the prompt textarea and change it
    const textareas = screen.getAllByRole("textbox");
    const promptArea = textareas[0];
    fireEvent.change(promptArea, {
      target: { value: "# Modified prompt" },
    });

    // Should show dirty badge now
    expect(screen.getByText("已修改")).toBeDefined();
  });

  it("shows run result when 试运行 is clicked", async () => {
    render(<PromptLabPanel />);
    await screen.findByText("Prompt Lab");

    // Click 试运行
    fireEvent.click(screen.getByText("试运行"));

    await waitFor(() => {
      expect(screen.getByText("分析结果")).toBeDefined();
    });

    // Should show tool calls
    expect(screen.getByText("Tool Calls")).toBeDefined();
    expect(screen.getByText(/get_stats/)).toBeDefined();
  });

  it("shows audit result separately from apply result", async () => {
    render(<PromptLabPanel />);
    await screen.findByText("Prompt Lab");

    // Click 审计 lessons
    fireEvent.click(screen.getByText("审计 lessons"));

    await waitFor(() => {
      expect(screen.getByText("审计结果")).toBeDefined();
    });
  });

  it("renders tabs: output, compare, gate, messages", async () => {
    render(<PromptLabPanel />);
    await screen.findByText("Prompt Lab");

    expect(screen.getByText("输出")).toBeDefined();
    expect(screen.getByText("对比")).toBeDefined();
    expect(screen.getByText("Gate")).toBeDefined();
    expect(screen.getByText("Messages")).toBeDefined();
  });
});
