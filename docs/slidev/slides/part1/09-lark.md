---
layout: section
class: text-center
---

# 9. Lark - Parsing and DSLs

<div class="text-lg text-secondary mt-4">
Building robust parsers with formal grammars
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">8 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">EBNF Grammars</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">AST Transformation</span>
  </div>
</div>

<!--
Section 9 covers Lark - the parsing toolkit that powers Maverick's expression DSL.

We'll cover:
1. What is Lark and why use it
2. Grammar syntax (EBNF notation)
3. Building your first grammar
4. Understanding parse trees
5. Transformers for AST generation
6. Maverick's expression grammar
7. Expression evaluation
8. Template string interpolation
-->

---

## layout: two-cols

# 9.1 What is Lark?

<div class="pr-4">

**Lark** is a modern parsing toolkit for Python

<div v-click class="mt-4">

## Why Parsers Matter

<div class="space-y-3 text-sm mt-3">

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>DSL Interpretation</strong>
    <div class="text-muted">Parse <code>${{ inputs.name }}</code> syntax</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>Robust Error Handling</strong>
    <div class="text-muted">Clear error messages with position info</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>Formal Specification</strong>
    <div class="text-muted">Grammar is the documentation</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal font-bold">◆</span>
  <div>
    <strong>Extensibility</strong>
    <div class="text-muted">Add new syntax without rewriting</div>
  </div>
</div>

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## The Wrong Approach ❌

```python
# Regex-based parsing - DON'T DO THIS
import re

def parse_expression(text):
    # Gets complex fast, hard to maintain
    match = re.match(
        r"\$\{\{\s*(inputs|steps)\.(\w+)"
        r"(?:\.(\w+))?(?:\[(\d+)\])?\s*\}\}",
        text
    )
    if match:
        return match.groups()  # Tuple soup!
```

<div class="text-xs text-muted mt-2">
Problems: Fragile, no clear error messages, hard to extend
</div>

</div>

<div v-click class="mt-4">

## The Lark Way ✓

```python
from lark import Lark

grammar = """
    start: "inputs" "." IDENTIFIER
    IDENTIFIER: /[a-zA-Z_]\w*/
"""

parser = Lark(grammar)
tree = parser.parse("inputs.name")  # Clean AST!
```

<div class="text-xs text-muted mt-2">
Clear grammar, automatic error handling, extensible
</div>

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Maverick Uses Lark</strong> for all <code>${{ }}</code> expression parsing in workflows. The grammar is the single source of truth.
</div>

</div>

<!--
Why Lark instead of regular expressions?

**DSL Interpretation**: Maverick's workflow expressions like ${{ inputs.name }} and ${{ steps.analyze.output.status }} need proper parsing - not regex hacks.

**Error Handling**: When a user writes an invalid expression, they need to know exactly what's wrong and where. Regex just says "didn't match."

**Formal Specification**: The Lark grammar file IS the specification. You can read it and understand exactly what syntax is valid.

**Extensibility**: Adding ternary expressions (${{ a if b else c }}) to Maverick was straightforward - just extend the grammar.

The regex approach seems simpler at first, but quickly becomes unmaintainable. Lark scales to real complexity.
-->

---

## layout: default

# 9.2 Grammar Syntax

<div class="text-secondary text-sm mb-4">
EBNF notation for defining language rules
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Basic Structure

```lark
// Rules (lowercase) - structural patterns
rule_name: pattern

// Terminals (UPPERCASE) - leaf tokens
TERMINAL: /regex_pattern/

// Comments
// This is a comment
```

</div>

<div v-click class="mt-4">

### Operators

```lark
// Sequence - A followed by B
rule: A B

// Alternation - A or B
rule: A | B

// Optional - zero or one
rule: A?

// Zero or more
rule: A*

// One or more
rule: A+

// Grouping
rule: (A B)+
```

</div>

</div>

<div>

<div v-click>

### Rule Modifiers

```lark {1-2|4-5|7-8|all}
// Normal rule - creates tree node
rule: pattern

// Inline rule (?) - passes children up
?rule: pattern

// Terminal rule (!) - keeps as-is
!rule: pattern
```

</div>

<div v-click class="mt-4">

### Terminals

```lark
// Literal strings
"hello"
'world'

// Regular expressions
IDENTIFIER: /[a-zA-Z_]\w*/
NUMBER: /\d+/
STRING: /"[^"]*"/ | /'[^']*'/

// Anonymous terminals (underscore prefix)
_WHITESPACE: /\s+/
```

</div>

<div v-click class="mt-4">

### Special Directives

```lark
// Ignore whitespace
%ignore /\s+/

// Import from other grammars
%import common.WS
%import common.NUMBER
```

</div>

</div>

</div>

<!--
Lark uses EBNF (Extended Backus-Naur Form) for grammar definition.

**Rules vs Terminals**: Rules are structural patterns (how things combine), terminals are the actual characters being matched.

**Operators**: The standard regex-like operators: `?` for optional, `*` for zero-or-more, `+` for one-or-more.

**Rule Modifiers**: The `?` prefix is key - it "inlines" the rule, passing children directly to the parent. This keeps your AST clean.

**Terminals**: Can be literal strings or regex patterns. UPPERCASE by convention.

**Ignore directive**: Essential for whitespace handling - makes it invisible to the grammar while still working.
-->

---

## layout: default

# 9.3 Your First Grammar

<div class="text-secondary text-sm mb-4">
Building a simple expression parser
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### A Simple Calculator Grammar

```lark
// Grammar: simple arithmetic expressions
?start: expr

?expr: term (("+" | "-") term)*
?term: factor (("*" | "/") factor)*
?factor: NUMBER
       | "(" expr ")"
       | "-" factor -> neg

NUMBER: /\d+(\.\d+)?/

%ignore /\s+/
```

</div>

<div v-click class="mt-4">

### Using the Parser

```python
from lark import Lark

grammar = open("calc.lark").read()
parser = Lark(grammar)

# Parse an expression
tree = parser.parse("2 + 3 * 4")
print(tree.pretty())
```

</div>

</div>

<div>

<div v-click>

### Parse Tree Output

```text
expr
  term
    factor
      2
  term
    factor
      3
    factor
      4
```

<div class="text-xs text-muted mt-2">
Tree structure reflects grammar rules
</div>

</div>

<div v-click class="mt-4">

### Parser Algorithms

<div class="space-y-2 text-sm">

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">parser="lalr"</code>
  <div class="text-muted text-xs mt-1">Fast, handles most grammars (Maverick uses this)</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">parser="earley"</code>
  <div class="text-muted text-xs mt-1">Handles ambiguous grammars, slower</div>
</div>

</div>

```python
# Maverick's parser configuration
parser = Lark(
    grammar,
    parser="lalr",      # Fast LALR(1) parser
    start="start",      # Entry rule
    propagate_positions=True,  # Track positions
)
```

</div>

</div>

</div>

<!--
Let's build a simple calculator to understand the basics.

**Grammar Structure**: We define expressions as terms combined with + or -, terms as factors combined with * or /. This gives us correct operator precedence.

**The ? modifier**: Notice the `?` prefix on rules. This "inlines" the rule - if a rule has only one child, that child is returned directly instead of wrapping it.

**Parser Algorithms**: LALR is fast and handles most practical grammars. Earley can handle ambiguous grammars but is slower. Maverick uses LALR for performance.

**propagate_positions**: This is crucial for error messages - it tracks where each token appears in the input.
-->

---

## layout: default

# 9.4 Parse Trees

<div class="text-secondary text-sm mb-4">
Understanding Lark's tree output
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Tree Structure

```python
from lark import Lark, Tree, Token

grammar = """
    start: greeting NAME
    greeting: "hello" | "hi"
    NAME: /[A-Za-z]+/
"""

parser = Lark(grammar)
tree = parser.parse("hello Alice")

# Tree is the parsed structure
print(type(tree))  # <class 'lark.Tree'>
print(tree.data)   # 'start'
```

</div>

<div v-click class="mt-4">

### Accessing Tree Nodes

```python
# tree.children contains child nodes
for child in tree.children:
    if isinstance(child, Tree):
        print(f"Rule: {child.data}")
        print(f"Children: {child.children}")
    elif isinstance(child, Token):
        print(f"Token: {child.type} = {child.value}")
```

**Output:**

```text
Rule: greeting
Children: [Token('HELLO', 'hello')]
Token: NAME = Alice
```

</div>

</div>

<div>

<div v-click>

### Tree vs Token

<div class="space-y-3 text-sm">

<div class="p-3 rounded border border-teal/30 bg-teal/5">
  <code class="text-teal font-bold">Tree</code>
  <div class="text-muted text-sm mt-1">
    Non-terminal (rule matches)<br/>
    Has <code>.data</code> (rule name) and <code>.children</code>
  </div>
</div>

<div class="p-3 rounded border border-brass/30 bg-brass/5">
  <code class="text-brass font-bold">Token</code>
  <div class="text-muted text-sm mt-1">
    Terminal (actual text matched)<br/>
    Has <code>.type</code> (terminal name) and <code>.value</code>
  </div>
</div>

</div>

</div>

<div v-click class="mt-4">

### Pretty Printing

```python
# Visualize the tree structure
print(tree.pretty())
```

```text
start
  greeting
    hello
  Alice
```

<div class="text-xs text-muted mt-2">
Indentation shows parent-child relationships
</div>

</div>

<div v-click class="mt-4">

### Finding Nodes

```python
# Find all nodes matching a pattern
names = tree.find_data("greeting")
for g in names:
    print(g.children)  # ['hello']

# Find all tokens of a type
tokens = tree.scan_values(
    lambda t: t.type == "NAME"
)
```

</div>

</div>

</div>

<!--
When Lark parses input, it produces a tree structure.

**Tree class**: Represents non-terminal rules. Has a `.data` attribute with the rule name, and `.children` with the matched sub-elements.

**Token class**: Represents terminal matches (the actual text). Has `.type` (the terminal name like NUMBER or NAME) and `.value` (the actual string).

**Pretty printing**: The `tree.pretty()` method is invaluable for debugging - it shows the tree structure with indentation.

**Navigation methods**: `find_data()` lets you find all subtrees matching a rule name. `scan_values()` lets you find tokens matching a condition.
-->

---

## layout: default

# 9.5 Transformers

<div class="text-secondary text-sm mb-4">
Converting parse trees to custom objects
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### The Transformer Class

```python {1-3|5-8|10-14|all}
from lark import Transformer, v_args

@v_args(inline=True)  # Unpack children as args

class CalcTransformer(Transformer):
    """Transform parse tree into computed values."""

    # Methods named after rules
    def NUMBER(self, token):
        """Transform NUMBER terminal."""
        return float(token.value)

    def neg(self, value):
        """Handle negation: "-" factor -> neg"""
        return -value

    def expr(self, *terms):
        """Combine terms (simplified)."""
        return sum(terms)
```

</div>

<div v-click class="mt-4">

### Using the Transformer

```python
tree = parser.parse("2 + 3 * 4")

# Transform the tree
transformer = CalcTransformer()
result = transformer.transform(tree)

print(result)  # 14.0 (if we handled * correctly)
```

</div>

</div>

<div>

<div v-click>

### How It Works

```text
Parse Tree:           After Transform:
┌──────────┐
│   expr   │ ──────►  14.0
├──────────┤
│ ┌──────┐ │
│ │term 2│ │ ──────►  2.0
│ └──────┘ │
│ ┌──────┐ │
│ │term  │ │ ──────►  12.0
│ │3 * 4 │ │
│ └──────┘ │
└──────────┘
```

<div class="text-xs text-muted mt-2">
Bottom-up: leaves first, then parents
</div>

</div>

<div v-click class="mt-4">

### @v_args Decorator

```python
# Without @v_args - children as list
def rule(self, children):
    a, b = children[0], children[1]

# With @v_args(inline=True) - unpacked
def rule(self, a, b):
    # Direct access to children
    pass

# With @v_args(tree=True) - get Tree object
def rule(self, tree):
    # Access tree.children, tree.data, etc.
    pass
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Key Insight:</strong> Transformer methods are named after grammar rules. Lark calls them automatically during tree traversal.
</div>

</div>

</div>

<!--
Transformers are where the magic happens - converting the raw parse tree into useful objects.

**Method naming**: Each method is named after a rule in your grammar. Lark automatically calls the right method for each tree node.

**@v_args decorator**: Controls how children are passed. `inline=True` is the most common - it unpacks children as function arguments.

**Bottom-up traversal**: Transformers work bottom-up. Leaf nodes are transformed first, then their results are passed to parent rules.

This pattern is exactly how Maverick transforms ${{ inputs.name }} into Expression objects with kind, path, and negated fields.
-->

---

## layout: default

# 9.6 Maverick Expression Grammar

<div class="text-secondary text-sm mb-4">
The <code>${{ }}</code> syntax that powers workflows
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Expression Syntax

```yaml
# In workflow YAML files:
steps:
  - name: greet
    type: python
    action: format_greeting
    kwargs:
      name: ${{ inputs.name }} # Input ref
      prev: ${{ steps.init.output }} # Step ref
      item: ${{ item.field }} # Loop item
      idx: ${{ index }} # Loop index
      msg: "Hello ${{ inputs.name }}!" # Template
```

</div>

<div v-click class="mt-4">

### The Grammar File

```lark
// src/maverick/dsl/expressions/grammar.lark

// Entry point - ternary has lowest precedence
start: ternary_expr

// Ternary: value if condition else other
?ternary_expr: bool_expr
    | bool_expr "if" bool_expr "else" ternary_expr

// Boolean expressions
?bool_expr: bool_term (_OR bool_term)*
?bool_term: unary_expr (_AND unary_expr)*
?unary_expr: negation unary_expr -> negated_expr
           | reference
```

</div>

</div>

<div>

<div v-click>

### Reference Types

```lark
// Four kinds of references
reference: input_ref
         | step_ref
         | item_ref
         | index_ref

// inputs.name, inputs.config.timeout
input_ref: "inputs" accessor+

// steps.analyze.output, steps.x.output.status
step_ref: "steps" "." IDENTIFIER "." "output" accessor*

// item, item.name, item[0]
item_ref: "item" accessor*

// index (no nested access)
index_ref: "index"
```

</div>

<div v-click class="mt-4">

### Accessors

```lark
// Dot or bracket notation
accessor: dot_accessor
        | bracket_accessor

dot_accessor: "." IDENTIFIER
bracket_accessor: "[" (INT | STRING) "]"

// Examples:
// .name        → dot_accessor
// [0]          → bracket_accessor (index)
// ["key"]      → bracket_accessor (string)
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Live in Maverick:</strong> See <code>src/maverick/dsl/expressions/grammar.lark</code> for the complete grammar.
</div>

</div>

</div>

<!--
Let's look at Maverick's actual expression grammar.

**Expression Types**: We support four reference types - inputs, steps, item (for loops), and index (loop counter).

**Accessors**: Both dot notation (`.field`) and bracket notation (`[0]` or `["key"]`) are supported for nested access.

**Ternary Support**: The grammar handles `${{ value_if_true if condition else value_if_false }}` for conditional expressions.

**Boolean Operators**: `and`, `or`, and `not` are supported with proper precedence (not > and > or).

The grammar is about 60 lines and handles all of Maverick's expression needs. This is the power of formal grammars - complex syntax, simple specification.
-->

---

## layout: default

# 9.7 Expression Evaluation

<div class="text-secondary text-sm mb-4">
The <code>ExpressionEvaluator</code> class
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Parsed Expression Types

```python
@dataclass(frozen=True, slots=True)
class Expression:
    """Single reference expression."""
    raw: str           # "${{ inputs.name }}"
    kind: ExpressionKind  # INPUT_REF, STEP_REF, etc.
    path: tuple[str, ...]  # ("inputs", "name")
    negated: bool = False

@dataclass(frozen=True, slots=True)
class BooleanExpression:
    """Compound boolean expression."""
    raw: str
    operator: str      # "and" or "or"
    operands: tuple[Expression, ...]

@dataclass(frozen=True, slots=True)
class TernaryExpression:
    """Conditional expression."""
    raw: str
    condition: AnyExpression
    value_if_true: AnyExpression
    value_if_false: AnyExpression
```

</div>

</div>

<div>

<div v-click>

### ExpressionEvaluator

```python {1-8|10-16|18-24|all}
from maverick.dsl.expressions import (
    ExpressionEvaluator,
    parse_expression,
)

# Create evaluator with context
evaluator = ExpressionEvaluator(
    inputs={"name": "Alice", "dry_run": False},
    step_outputs={
        "analyze": {
            "output": {
                "status": "success",
                "files": ["a.py", "b.py"],
            }
        }
    },
)

# Parse and evaluate
expr = parse_expression("${{ inputs.name }}")
result = evaluator.evaluate(expr)
print(result)  # "Alice"

expr = parse_expression("${{ steps.analyze.output.files[0] }}")
result = evaluator.evaluate(expr)
print(result)  # "a.py"
```

</div>

<div v-click class="mt-4">

### Negation & Booleans

```python
# Negated expression
expr = parse_expression("${{ not inputs.dry_run }}")
result = evaluator.evaluate(expr)  # True

# Boolean expression
expr = parse_expression("${{ inputs.flag and not inputs.skip }}")
result = evaluator.evaluate(expr)  # depends on values
```

</div>

</div>

</div>

<!--
The Transformer converts parse trees into these dataclasses, then the Evaluator resolves them.

**Expression**: Single reference with a path to navigate. The `kind` tells us where to look (inputs vs steps vs item).

**BooleanExpression**: Multiple expressions combined with `and` or `or`. Operands are evaluated and combined.

**TernaryExpression**: Conditional with three parts - condition, true value, false value.

**ExpressionEvaluator**: Takes the workflow context (inputs and step outputs) and resolves expression paths through it.

The path tuple `("steps", "analyze", "output", "files", "0")` is navigated step by step through the nested dictionaries.
-->

---

## layout: default

# 9.8 Template Interpolation

<div class="text-secondary text-sm mb-4">
Mixing literal text with expressions
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Template Strings

```yaml
# In workflow YAML
steps:
  - name: create_message
    type: python
    action: format_message
    kwargs:
      message: |
        Hello ${{ inputs.user }}!

        Your analysis of ${{ inputs.repo }} is complete.
        Files changed: ${{ steps.analyze.output.count }}
        Status: ${{ steps.validate.output.status }}
```

<div class="text-xs text-muted mt-2">
Multiple expressions embedded in a single string
</div>

</div>

<div v-click class="mt-4">

### How It Works

```python
# The evaluate_string method handles templates
template = (
    "Hello ${{ inputs.name }}, "
    "status: ${{ steps.check.output.status }}"
)

result = evaluator.evaluate_string(template)
# "Hello Alice, status: success"
```

</div>

</div>

<div>

<div v-click>

### Implementation

```python {1-6|8-15|17-24|all}
# Extract all expressions from text
def extract_all(text: str) -> list[AnyExpression]:
    """Find all ${{ }} in text."""
    pattern = r"\$\{\{\s*(.*?)\s*\}\}"
    matches = re.findall(pattern, text)
    return [parse_expression(m) for m in matches]

# Evaluate and replace
def evaluate_string(self, text: str) -> str:
    """Evaluate all expressions in text."""
    result = text
    for expr in extract_all(text):
        value = self.evaluate(expr)
        result = result.replace(expr.raw, str(value))
    return result

# Example usage
evaluator = ExpressionEvaluator(
    inputs={"name": "Bob", "count": 5},
    step_outputs={"step1": {"output": "done"}},
)

template = "User ${{ inputs.name }} has ${{ inputs.count }} items"
result = evaluator.evaluate_string(template)
# "User Bob has 5 items"
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Complete Flow:</strong>
  <div class="mt-1 text-xs">
    1. <code>extract_all()</code> finds all <code>${{ }}</code> patterns<br/>
    2. <code>parse_expression()</code> converts each to AST<br/>
    3. <code>evaluate()</code> resolves against context<br/>
    4. Replace original patterns with values
  </div>
</div>

</div>

</div>

<!--
Template interpolation is the final piece - embedding multiple expressions in text.

**The Pattern**: Templates can have any number of ${{ }} expressions mixed with literal text.

**extract_all**: First, we find all expression patterns in the text using a simple regex.

**Parse Each**: Each matched expression is parsed using the Lark grammar we defined.

**Evaluate and Replace**: Finally, we evaluate each expression and replace the original ${{ ... }} with the resulting value.

This powers Maverick's dynamic message generation, commit messages, and any string that needs runtime values.
-->

---

layout: center
class: text-center

---

# Section 9 Summary

<div class="grid grid-cols-3 gap-6 mt-8 text-left max-w-4xl mx-auto">

<div v-click class="p-4 rounded-lg border border-teal/30 bg-teal/5">
  <div class="text-teal font-bold mb-2">Grammar Definition</div>
  <div class="text-sm text-muted">
    EBNF notation defines valid syntax. Rules combine with operators (<code>*</code>, <code>+</code>, <code>?</code>, <code>|</code>).
  </div>
</div>

<div v-click class="p-4 rounded-lg border border-brass/30 bg-brass/5">
  <div class="text-brass font-bold mb-2">Parse Trees</div>
  <div class="text-sm text-muted">
    <code>Tree</code> nodes for rules, <code>Token</code> nodes for terminals. Navigate with <code>.children</code>, <code>.data</code>.
  </div>
</div>

<div v-click class="p-4 rounded-lg border border-coral/30 bg-coral/5">
  <div class="text-coral font-bold mb-2">Transformers</div>
  <div class="text-sm text-muted">
    Convert parse trees to custom objects. Methods named after rules, <code>@v_args</code> for convenience.
  </div>
</div>

</div>

<div class="mt-8" v-click>

### Maverick's Expression System

```text
YAML Template          Grammar           AST                    Evaluator           Result
"${{ inputs.name }}" → grammar.lark → Expression(path=...) → ExpressionEvaluator → "Alice"
```

</div>

<div class="mt-6 text-sm text-muted" v-click>

**Key Files:**
[src/maverick/dsl/expressions/grammar.lark](../../src/maverick/dsl/expressions/grammar.lark) •
[src/maverick/dsl/expressions/parser.py](../../src/maverick/dsl/expressions/parser.py) •
[src/maverick/dsl/expressions/evaluator.py](../../src/maverick/dsl/expressions/evaluator.py)

</div>

<!--
Let's summarize what we learned about Lark:

**Grammar Definition**: Formal EBNF grammars are clearer than regex and scale to real complexity. Maverick's grammar is ~60 lines.

**Parse Trees**: Lark produces Tree and Token objects. The `?` modifier and `propagate_positions` are key for clean ASTs and good errors.

**Transformers**: Method-based conversion from parse trees to domain objects. The @v_args decorator controls argument passing.

**Complete Pipeline**: Template string → extract expressions → parse with grammar → transform to AST → evaluate against context → final value.

This is the foundation for Maverick's dynamic workflow system. Understanding Lark helps you extend the expression syntax or debug parsing issues.
-->
