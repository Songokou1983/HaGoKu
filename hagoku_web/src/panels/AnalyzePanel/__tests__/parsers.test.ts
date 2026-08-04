import { describe, it, expect } from "vitest";
import { significanceShort, resolveAgentKey } from "../parsers";

describe("significanceShort", () => {
  it('returns "显著" for "significant"', () => {
    expect(significanceShort("significant")).toBe("显著");
  });

  it('returns "未显著" for "not_significant"', () => {
    expect(significanceShort("not_significant")).toBe("未显著");
  });

  it('returns trimmed string for unknown values', () => {
    expect(significanceShort("  custom  ")).toBe("custom");
  });

  it('returns "—" for empty string', () => {
    expect(significanceShort("")).toBe("—");
  });
});

describe("resolveAgentKey", () => {
  it('returns "scout" for scout agent', () => {
    expect(resolveAgentKey("scout")).toBe("scout");
  });

  it('returns "cleaner" for clean agent', () => {
    expect(resolveAgentKey("cleaner_agent")).toBe("cleaner");
  });

  it('returns "analyst" for analys agent', () => {
    expect(resolveAgentKey("analyst_0")).toBe("analyst");
  });

  it('returns "reporter" for report agent', () => {
    expect(resolveAgentKey("reporter_1")).toBe("reporter");
  });

  it("returns null for unknown agent", () => {
    expect(resolveAgentKey("unknown")).toBeNull();
  });
});
