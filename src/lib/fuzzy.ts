/**
 * Typo-tolerant search: a query matches a set of fields when it is a
 * case-insensitive substring of one of them, or when every whitespace-separated
 * word is within a few edits of some substring of one of them.
 *
 * Not a subsequence match: "firebase" spelled out letter by letter across a
 * long licence string is not a hit, which is what made "select all shown"
 * grab qemu packages.
 *
 * Per word this is approximate substring matching (Sellers' edit distance,
 * where the match may start and end anywhere in the text), computed with
 * Myers' bit-parallel algorithm: one pass over the text per word, a handful of
 * integer operations per character. 13k rows filter in a few milliseconds.
 */

/**
 * 0: the whole query is a substring. 1: every word matched within its typo
 * budget, each match starting on the word's first letter. 2: the same, with
 * some match starting elsewhere ("firbase" -> "airbase" ranks after
 * "firebase": a typo in the first letter is the rarer kind).
 */
export type Rank = 0 | 1 | 2;

export interface CompiledQuery {
  /**
   * The rank of the best match over `fields`, or null for no match.
   */
  readonly rank: (fields: readonly string[]) => null | Rank;
}

/**
 * Myers' bit vectors hold one bit per pattern character in a 32-bit integer.
 */
const MAX_PATTERN = 32;
const ASCII = 128;

/**
 * The edit budget for one word. Short words get none: one edit on a
 * three-letter word matches nearly anything containing two of its letters.
 */
export function maxTypos(word: string): number {
  if (word.length >= 8) return 2;
  return word.length >= 4 ? 1 : 0;
}

interface Pattern {
  /**
   * Bit i set where the pattern's character i is this code unit: a flat
   * table for ASCII (the hot path), a map for everything else.
   */
  readonly ascii: Int32Array;
  readonly peq: Map<number, number>;
  readonly text: string;
  readonly typos: number;
}

interface Word extends Pattern {
  /**
   * `typos + 1` consecutive slices of the word. Each edit breaks at most one,
   * so any match leaves one intact: a native `includes` on these rules out
   * nearly every row before the bit-vector pass runs.
   */
  readonly pieces: readonly string[];
  /**
   * The word minus its first letter, for the anchored check.
   */
  readonly tail: Pattern;
}

function compilePattern(text: string, typos: number): Pattern {
  const peq = new Map<number, number>();
  for (let index = 0; index < text.length; index++) {
    // Code units, not code points: the text is walked the same way below.
    // eslint-disable-next-line unicorn/prefer-code-point
    const code = text.charCodeAt(index);
    peq.set(code, (peq.get(code) ?? 0) | (1 << index));
  }
  const ascii = new Int32Array(ASCII);
  for (const [code, bits] of peq) if (code < ASCII) ascii[code] = bits;
  return { ascii, peq, text, typos };
}

/**
 * Balanced: "com.google" in 3 is "com." "goo" "gle", never a 2-letter tail.
 */
function slices(text: string, count: number): string[] {
  const cut = (index: number): number => Math.round((index * text.length) / count);
  return Array.from({ length: count }, (_, index) => text.slice(cut(index), cut(index + 1)));
}

function compileWord(text: string): Word {
  const typos = maxTypos(text);
  return {
    ...compilePattern(text, typos),
    pieces: slices(text, typos + 1),
    tail: compilePattern(text.slice(1), typos),
  };
}

/**
 * Patterns Myers cannot hold, or with no budget, need an exact hit.
 */
function isExactOnly(pattern: Pattern): boolean {
  return pattern.typos === 0 || pattern.text.length > MAX_PATTERN;
}

/**
 * True when `pattern` is within its edit budget of a substring of `text`
 * from `start` on. Myers (1999): unanchored, the top DP row is all zeros (no
 * carry-in); anchored, it counts up from `start` (carry-in 1), so the match
 * must begin there.
 */
function isWithinTypos(pattern: Pattern, text: string, start = 0, isAnchored = false): boolean {
  const { ascii, peq, typos } = pattern;
  const length = pattern.text.length;
  const carry = isAnchored ? 1 : 0;
  const high = 1 << (length - 1);
  let pv = -1;
  let mv = 0;
  let score = length;
  for (let index = start; index < text.length; index++) {
    // eslint-disable-next-line unicorn/prefer-code-point
    const code = text.charCodeAt(index);
    // Out of the table's range a typed array reads undefined: the map's turn.
    const eq = ascii[code] ?? peq.get(code) ?? 0;
    const xv = eq | mv;
    const xh = (((eq & pv) + pv) ^ pv) | eq;
    let ph = mv | ~(xh | pv);
    let mh = pv & xh;
    if ((ph & high) !== 0) score++;
    else if ((mh & high) !== 0) score--;
    if (score <= typos) return true;
    ph = (ph << 1) | carry;
    mh <<= 1;
    pv = mh | ~(xv | ph);
    mv = ph & xv;
  }
  return false;
}

function matchesWord(word: Word, field: string): boolean {
  return isExactOnly(word)
    ? field.includes(word.text)
    : word.pieces.some((piece) => field.includes(piece)) && isWithinTypos(word, field);
}

/**
 * A match that starts on the word's first letter, typos only after it.
 */
function matchesAnchored(word: Word, field: string): boolean {
  if (isExactOnly(word)) return field.includes(word.text);
  const first = word.text.charAt(0);
  for (let index = field.indexOf(first); index !== -1; index = field.indexOf(first, index + 1)) {
    if (isWithinTypos(word.tail, field, index + 1, true)) return true;
  }
  return false;
}

export function compileQuery(query: string): CompiledQuery {
  const whole = query.trim().toLowerCase();
  const words = whole.split(/\s+/u).map((word) => compileWord(word));
  return {
    rank(fields: readonly string[]): null | Rank {
      if (whole === "") return 0;
      const lowered = fields.map((field) => field.toLowerCase());
      if (lowered.some((field) => field.includes(whole))) return 0;
      if (words.some((word) => lowered.every((field) => !matchesWord(word, field)))) return null;
      return words.every((word) => lowered.some((field) => matchesAnchored(word, field))) ? 1 : 2;
    },
  };
}
