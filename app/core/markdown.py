r"""Fix-ups applied to model output before it is saved.

Two things models write that Obsidian will not render:

- LaTeX in the `\(x\)` / `\[x\]` form. Obsidian reads only `$x$` / `$$x$$`, so a
  document full of the first shows literal backslashes to the reader.
- Mermaid node labels holding unquoted parentheses, which is a parse error — the
  whole diagram silently renders as nothing.

Direction is a preference rather than a bug: `LR` diagrams run off the side of a
note, so they are turned upright.
"""

import re

# Fenced blocks and inline code are copied through untouched: a code sample may
# legitimately contain \( or \[ (a regex, a shell escape) and rewriting it is a bug.
# Mermaid is the one fence with its own pass — see _fence().
PROTECTED = re.compile(
    r"(^[ \t]*```.*?^[ \t]*```[ \t]*$|^[ \t]*~~~.*?^[ \t]*~~~[ \t]*$|`[^`\n]+`)",
    re.DOTALL | re.MULTILINE,
)

# `\\[4pt]` is a LaTeX line-break with a spacing argument, not an opener — the
# lookbehind keeps the second backslash of a `\\` pair from being read as one.
DISPLAY = re.compile(r"(?<!\\)\\\[(.+?)(?<!\\)\\\]", re.DOTALL)
INLINE = re.compile(r"(?<!\\)\\\((.+?)\\\)", re.DOTALL)

# Money written as a bare `$` opens a math span and swallows the prose up to the next
# one — "costs $5 a unit, or $120 a month" renders the middle as a formula. A candidate
# span holding no LaTeX at all is prose caught between two currency signs, so the sign
# is escaped; one that does hold LaTeX is a formula that merely starts with a digit.
# The closing `$` is a lookahead, never consumed — the next sign in "costs $5 or $120"
# must still be available to start its own match.
CURRENCY = re.compile(r"(?<![\\$])\$(\d[\d,.]*(?:[\s)\]%,.]|$)[^$\n]*)(?=\$|$)", re.MULTILINE)
LATEX = re.compile(r"[\\^_{}]")

# A wide diagram is unreadable in a note column, so LR/RL become top-down.
DIRECTION = re.compile(r"^([ \t]*)(graph|flowchart)([ \t]+)(?:LR|RL)\b", re.MULTILINE)

# `A[Label (with parens)]` is a mermaid parse error. Quoting the label fixes it.
# Only a plain `id[...]` is touched: `[[`, `([` and `[(` are shape wrappers, and
# quoting those would change the node's shape instead of just rescuing the text.
LABEL = re.compile(r"(?<![\[(\w])(\w[\w-]*)\[(?!\()([^\[\]\"\n]*[()][^\[\]\"\n]*)\]")


def normalize(text: str) -> str:
    """Rewrite math delimiters, and repair mermaid blocks."""
    parts = PROTECTED.split(text)
    # split() with one capture group alternates unprotected, protected, unprotected, …
    return "".join(_fence(p) if index % 2 else _math(p) for index, p in enumerate(parts))


def _math(chunk: str) -> str:
    chunk = CURRENCY.sub(_money, chunk)
    # The interior is copied verbatim: a block indented inside a list item keeps that
    # indent, so the math stays part of the item instead of breaking out of the list.
    chunk = DISPLAY.sub(lambda m: f"$${m.group(1)}$$", chunk)
    return INLINE.sub(lambda m: f"${m.group(1).strip()}$", chunk)


def _money(match: re.Match) -> str:
    if LATEX.search(match.group(1)):
        return match.group(0)  # a formula that merely starts with a digit
    return f"\\${match.group(1)}"


def _fence(chunk: str) -> str:
    if not chunk.lstrip().startswith("```mermaid"):
        return chunk
    chunk = DIRECTION.sub(r"\1\2\3TD", chunk)
    return LABEL.sub(r'\1["\2"]', chunk)
