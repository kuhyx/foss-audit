/**
 * Inline stylesheet for the static docs pages and 404.html. They load no
 * bundle, so they cannot use the app's hashed CSS; the values follow the
 * shared palette (charcoal text, the accent for links).
 */
export const STYLE = [
  "body{margin:0;background:#faf8f5;color:#211d1b;font:16px/1.6 system-ui,sans-serif}",
  ".doc{max-width:44rem;margin:0 auto;padding:32px 16px}",
  "h1{font-size:32px;line-height:1.2;margin:0 0 8px}",
  "h2{font-size:20px;margin:32px 0 8px}",
  ".lead{color:#5c5550;margin:0 0 24px}",
  "a{color:#8a6420}",
  "pre{background:#211d1b;color:#faf8f5;padding:16px;border-radius:8px;overflow-x:auto}",
  "dl div{display:flex;gap:16px;padding:4px 0}dt{min-width:9rem;font-weight:600}dd{margin:0}",
  ".codes{columns:3;padding-left:16px}",
].join("");
