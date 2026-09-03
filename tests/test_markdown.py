r"""The `\(x\)` → `$x$` swap applied to every saved document."""

from app.core.markdown import normalize


def test_inline_delimiters_become_single_dollars():
    text = r"\(x_{1A}\) = units shipped, and \(x_{ij} \ge 0\) for all i, j."

    assert normalize(text) == r"$x_{1A}$ = units shipped, and $x_{ij} \ge 0$ for all i, j."


def test_display_delimiters_become_a_dollar_block():
    text = "\\[\n\\min Z = 4x_{1A}\n\\]"

    assert normalize(text) == "$$\n\\min Z = 4x_{1A}\n$$"


def test_multiline_display_body_is_kept_intact():
    text = "\\[\n\\begin{aligned}\nx &\\le 120\\\\\ny &= 80\n\\end{aligned}\n\\]"

    out = normalize(text)

    assert out.startswith("$$\n\\begin{aligned}")
    assert out.endswith("\\end{aligned}\n$$")


def test_fenced_code_is_left_alone():
    """A regex in a code sample legitimately contains \\( — rewriting it is a bug."""
    text = '```python\npattern = re.compile(r"\\(group\\)")\n```'

    assert normalize(text) == text


def test_inline_code_is_left_alone():
    text = 'call `re.sub(r"\\(x\\)", "", s)` here'

    assert normalize(text) == text


def test_text_without_latex_is_untouched():
    text = "Already fine: $x$ inline and\n\n$$\ny = mx + b\n$$\n"

    assert normalize(text) == text


def test_latex_line_break_with_spacing_is_not_an_opener():
    r"""`\\[4pt]` inside an aligned block is a line break, not a display delimiter."""
    text = "$$\n\\begin{aligned}\na &= 1,\\\\[4pt]\nb &= 2\n\\end{aligned}\n$$"

    assert normalize(text) == text


def test_indented_block_keeps_its_indent():
    """A block inside a list item must stay indented, or it breaks out of the list."""
    text = "1. Axiom three:\n\n   \\[\n   P(A) = 1\n   \\]\n"

    assert normalize(text) == "1. Axiom three:\n\n   $$\n   P(A) = 1\n   $$\n"


def test_horizontal_diagrams_are_turned_upright():
    text = "```mermaid\ngraph LR\n    A --> B\n```"

    assert "flowchart TD" in normalize("```mermaid\nflowchart LR\n    A --> B\n```")
    assert "graph TD" in normalize(text)


def test_top_down_direction_is_left_alone():
    text = "```mermaid\nflowchart TD\n    A --> B\n```"

    assert normalize(text) == text


def test_parenthesised_label_is_quoted():
    """Unquoted parens are a mermaid parse error — the whole diagram renders as nothing."""
    text = "```mermaid\nflowchart TD\n    A[Ingestion (Kafka)] --> B[Store]\n```"

    assert 'A["Ingestion (Kafka)"]' in normalize(text)


def test_node_shapes_are_not_flattened_into_rectangles():
    """`[[`, `([` and `[(` are shapes; quoting them would change the node, not fix it."""
    text = "```mermaid\nflowchart TD\n    A[[Sub (x)]] --> B([Round (y)]) --> C[(Cyl (z))]\n```"

    assert normalize(text) == text


def test_direction_outside_a_mermaid_fence_is_untouched():
    text = "```python\nflowchart LR = 1\n```\n\nProse mentioning graph LR here.\n"

    assert normalize(text) == text


def test_currency_is_escaped_so_it_cannot_open_math():
    text = "It costs $5 a unit, or $120,000 a year."

    assert normalize(text) == r"It costs \$5 a unit, or \$120,000 a year."


def test_a_formula_starting_with_a_digit_is_not_mistaken_for_money():
    text = r"the ratio $1 - \frac{a}{b}$ and $1.282 \times 2.0 = 2.564$ hold"

    assert normalize(text) == text


def test_already_escaped_currency_is_left_alone():
    text = r"costs \$5 a unit"

    assert normalize(text) == text
