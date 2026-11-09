// Maximally aggressive, type-aware flat config.
//
// Baseline is typescript-eslint's *type-checked* strict + stylistic presets, so
// anything they flag is an error, not a warning. On top of that: unicorn (all),
// sonarjs (cognitive complexity / duplicate logic), perfectionist (sorting) and
// eslint-plugin-astro for `.astro` files. Unused disable directives are themselves errors, so every
// `eslint-disable` in this repo must be load-bearing.
//
// Deliberately absent:
//   - eslint-plugin-jsx-a11y: 6.10.2 declares peer ESLint "^3 || ... || ^9" — no
//                             ESLint 10 support yet. a11y is enforced by review
//                             and the e2e flows instead.
//
// TypeScript is pinned to 6.0.x, not 7.x: typescript-eslint requires
// "typescript >=4.8.4 <6.1.0", and losing every type-aware rule would be a far
// bigger regression than gaining the Go-native compiler.
import js from "@eslint/js";
import astro from "eslint-plugin-astro";
import perfectionist from "eslint-plugin-perfectionist";
import sonarjs from "eslint-plugin-sonarjs";
import unicorn from "eslint-plugin-unicorn";
import tseslint from "typescript-eslint";

const config = tseslint.config(
  {
    ignores: [
      ".astro",
      ".claude",
      "dist",
      "coverage",
      ".venv",
      "*.egg-info",
      "data",
      "fixtures",
      "foss_audit",
      "screenshots",
      "tests",
      // React leftovers: the reference implementation until each widget is
      // ported, then deleted. Not part of the build.
      "**/*.tsx",
    ],
  },
  { linterOptions: { reportUnusedDisableDirectives: "error" } },

  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  unicorn.configs.all,
  sonarjs.configs.recommended,
  perfectionist.configs["recommended-natural"],
  ...astro.configs.recommended,

  {
    files: ["**/*.ts"],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Numbers in template literals are unambiguous and pervasive here
      // (counts, percentages, SVG geometry).
      "@typescript-eslint/restrict-template-expressions": [
        "error",
        { allowNumber: true },
      ],

      // Keep the rule, widen its vocabulary. `passesFilters(server, filter)`
      // and `matchesQuery(...)` are predicates that read as English; forcing
      // them to `isPassingFilters` would be worse prose in service of a prefix
      // list. `passes`/`matches` are added, nothing is removed.
      "unicorn/consistent-boolean-name": [
        "error",
        { prefixes: { matches: true, passes: true } },
      ],

      // Kebab-case files; `.astro` layouts may be PascalCase (see below).
      "unicorn/filename-case": ["error", { case: "kebabCase" }],
    },
  },

  // House overrides, applied to every file including this config itself.
  //
  // Each rule below is switched off deliberately: these are the cases where
  // "more aggressive" makes the code worse rather than safer. A rule you must
  // disable at every use site is worse than no rule at all, because
  // reportUnusedDisableDirectives then turns the disables into their own debt.
  {
    rules: {
      // Directly contradicts unicorn/consistent-class-member-order: one wants
      // a private field before the getter that reads it, the other wants the
      // getter first, and satisfying either re-triggers the other. unicorn's
      // wins because "declare the field before the code that uses it" is a
      // reason, whereas alphabetical order within a class is not.
      "perfectionist/sort-classes": "off",

      // Sorts Map entries by key. The verdict and fit tables are in their
      // domain order (free -> not free, drop-in -> none); alphabetising them
      // would shred the order every view renders them in.
      "perfectionist/sort-maps": "off",

      // Alphabetises declarations within a file, which actively fights reading
      // order: it would scatter `GRADES -> gradeRank -> isTripleA` into
      // `compositeRank -> GRADES -> gradeCoverage`. Alphabetical order is not
      // narrative order. Every *other* perfectionist rule stays on — sorting
      // imports, union members and object keys destroys no narrative.
      "perfectionist/sort-modules": "off",

      // Wants JSDoc blocks written without leading `*`, which is neither the
      // TypeScript convention nor what editors/typedoc render.
      "unicorn/no-asterisk-prefix-in-documentation-comments": "off",

      // Flags hand-wrapped comment prose. Comments here are wrapped to 80
      // columns on purpose; the rule would force one long line per paragraph.
      "unicorn/no-manually-wrapped-comments": "off",

      // `null` is load-bearing: the API contract is JSON, which has no
      // `undefined`, and `version`, `url`, `alternative` and `removeCommand`
      // are all `null` when absent. The zod schema mirrors the wire format.
      "unicorn/no-null": "off",

      // `Temporal` does not exist in this project's runtime: Node 26 reports
      // `typeof Temporal === "undefined"`. The rule is unfollowable until it
      // ships. The input here is the scan's ISO-8601 `generatedAt`, which
      // Date.parse handles identically across engines — the cross-engine
      // inconsistency the rule warns about is for non-ISO strings.
      "unicorn/prefer-temporal": "off",

      // The domain vocabulary is abbreviated on purpose: `props`, `env`,
      // `pkg` and the contract's own `effortReason` would only get longer
      // without getting clearer.
      "unicorn/prevent-abbreviations": "off",
    },
  },

  {
    rules: {
      // Caps a try block at ONE statement. Unfollowable where several steps
      // can throw and all mean the same thing: the scan fetch wraps fetch(),
      // response.json() and the schema parse together, because any of them
      // failing means "no scan to show". The rule has no maximum option.
      "unicorn/try-complexity": "off",
    },
  },

  // Tests: relax the rules that fight with mocking and fixtures.
  {
    files: ["**/*.test.ts", "src/test/**"],
    rules: {
      "@typescript-eslint/no-empty-function": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/require-await": "off",
      "@typescript-eslint/unbound-method": "off",
      "sonarjs/no-duplicate-string": "off",
      // Test helpers live beside the tests that use them; hoisting every
      // fixture factory to module scope to satisfy a scoping rule would
      // scatter each test's setup away from the test.
      "unicorn/consistent-function-scoping": "off",
      // A no-op stub is the point of a stub.
      "unicorn/no-empty-file": "off",
    },
  },

  // The vitest setup file exists *to* perform top-level side effects: it patches
  // globals (ResizeObserver, layout metrics, pointer capture) that jsdom lacks,
  // before any test imports run. These two rules cannot be satisfied by a file
  // whose entire contract is "mutate the environment on import".
  {
    files: ["src/test/setup.ts"],
    rules: {
      // The stubs are property getters installed on DOM prototypes, so `this`
      // is the element being measured — there is no class to put them in.
      "unicorn/no-this-outside-of-class": "off",
      "unicorn/no-top-level-assignment-in-function": "off",
      "unicorn/no-top-level-side-effects": "off",
    },
  },

  // Plain JS config files and `.astro` pages get no type-aware linting:
  // projectService cannot see `.astro` files, `astro check` types them.
  {
    extends: [tseslint.configs.disableTypeChecked],
    files: ["**/*.{js,mjs,cjs,astro}"],
  },

  // Layouts are PascalCase by Astro convention; pages and endpoints stay
  // kebab-case ("404.astro" and "index.astro" satisfy both).
  {
    files: ["**/*.astro"],
    rules: {
      "unicorn/filename-case": ["error", { cases: { kebabCase: true, pascalCase: true } }],
      // Astro requires the frontmatter interface to be called `Props`.
      "unicorn/name-replacements": ["error", { replacements: { props: false } }],
      // Frontmatter is a module body: top-level side effects are its job.
      "unicorn/no-top-level-side-effects": "off",
    },
  },
);

export default config;
