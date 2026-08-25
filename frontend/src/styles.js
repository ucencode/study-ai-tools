/**
 * The handful of class strings used in four or more places. Everything used once or
 * twice is written inline at the element, which is the point of the Tailwind move —
 * this file exists only so the button and message styles aren't pasted seven times.
 *
 * Colour comes from the tokens in styles.css, never a literal.
 */

// Three button levels, and no more.
export const PRIMARY =
  "h-9 px-3.5 rounded-md text-sm font-medium bg-accent border border-accent text-white " +
  "not-disabled:hover:brightness-110";

export const SECONDARY_BUTTON =
  "h-9 px-3.5 rounded-md text-sm font-medium bg-panel border border-line text-fg " +
  "not-disabled:hover:border-accent";

export const QUIET =
  "px-1 bg-transparent border-0 text-sm text-muted underline underline-offset-[3px] " +
  "decoration-line not-disabled:hover:text-fg";

// `error` is the raw exception string, so these render it as-is and never prettify it.
export const INLINE_ERROR =
  "text-sm text-fail border border-fail rounded-md px-2.5 py-2 bg-fail/[7%]";

export const INLINE_WARNING = "text-xs text-warn";

export const ROW = "flex items-center gap-2.5 flex-wrap";

export const MUTED = "text-xs text-muted";
