import { html } from "./dom.ts";
import { verdictBadge } from "./verdict-badge.ts";

describe("html", () => {
  it("sets attributes, skips empty ones and appends children as text", () => {
    const node = html("a", { class: "x", disabled: true, hidden: false, href: null, tabindex: 0, title: undefined }, "<b>", 3, null);
    expect(node.outerHTML).toBe('<a class="x" disabled="" tabindex="0">&lt;b&gt;3</a>');
  });

  it("appends nodes as they are", () => {
    expect(html("p", {}, html("b", {}, "x")).outerHTML).toBe("<p><b>x</b></p>");
  });
});

describe("verdictBadge", () => {
  it("is a dot plus the label", () => {
    const badge = verdictBadge("nonfree");
    expect(badge.className).toBe("verdict");
    expect(badge.querySelector(".dot")?.getAttribute("aria-hidden")).toBe("true");
    expect(badge.textContent).not.toBe("");
  });
});
