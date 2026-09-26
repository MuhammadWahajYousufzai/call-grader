import { describe, expect, it } from "vitest";
import { fmtClock, scoreClass } from "../lib/format";

describe("frontend helpers", () => {
  it("formats clock", () => {
    expect(fmtClock(247.2)).toBe("04:07");
    expect(fmtClock(9)).toBe("00:09");
  });
  it("scores classify", () => {
    expect(scoreClass(9)).toContain("emerald");
    expect(scoreClass(7)).toContain("amber");
    expect(scoreClass(4)).toContain("red");
  });
});
