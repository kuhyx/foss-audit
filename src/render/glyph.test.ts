import { VIEW_TIPS } from "./glyph.ts";

describe("VIEW_TIPS", () => {
  it("is one hover word per view", () => {
    for (const tip of Object.values(VIEW_TIPS)) expect(tip).toMatch(/^[A-Za-z-]{1,20}$/);
  });
});