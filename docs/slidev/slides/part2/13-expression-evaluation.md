---
layout: section
class: text-center
---

# 13. Expression Evaluation Engine

<div class="text-lg text-secondary mt-4">
Resolving dynamic values in workflow definitions
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">11 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Grammar & Parsing</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Context Resolution</span>
  </div>
</div>

<!--
Section 13 covers Maverick's expression evaluation engine - the system that
resolves ${{ }} expressions into concrete values at runtime.

We'll cover:
1. Expression system overview
2. Expression syntax (${{ ... }})
3. Input references
4. Step output references
5. Iteration context (item, index)
6. Boolean operations
7. Ternary expressions
8. Template strings
9. The Lark grammar
10. Parser implementation
11. Evaluator implementation
-->

---
layout: two-cols
---

# 13.1 Expression System Overview

<div class="pr-4">

<div v-click>

## The Challenge

YAML is static, but workflows need dynamic values:

```yaml
steps:
  - name: greet
    type: python
    action: format_greeting
    args:
      # How do we pass the workflow input here?
      - ???
```

</div>

<div v-click class="mt-4">

## The Solution: Expressions

Lightweight DSL for referencing runtime values:

- **Inputs**: `${{ inputs.name }}`
- **Step outputs**: `${{ steps.x.output }}`
- **Iteration**: `${{ item }}`, `${{ index }}`
- **Logic**: `${{ not inputs.dry_run }}`

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Complete Example

```yaml {all|5|9|13|all}
version: "1.0"
name: dynamic-workflow

inputs:
  name:      # ← Define input
    type: string
    required: true

steps:
  - name: greet
    type: python
    action: format_greeting
    args:
      - ${{ inputs.name }}  # ← Use input

outputs:
  greeting: ${{ steps.greet.output }}  # ← Use output
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Key Insight</strong><br>
  Expressions enable data flow between steps without 
  hardcoding values - the foundation of reusable workflows.
</div>

</div>

<!--
Expressions are evaluated at runtime when the workflow executes.
The expression engine parses the syntax, looks up values in context,
and returns the resolved result.
-->

---
layout: two-cols
---

# 13.2 Expression Syntax

<div class="pr-4">

<div v-click>

## The `${{ }}` Delimiter

All expressions are wrapped in double curly braces with a dollar sign:

```text
${{ expression_content }}
```

<div class="text-sm text-muted mt-2">
  Similar to GitHub Actions, Jinja2, and other templating systems
</div>

</div>

<div v-click class="mt-6">

## Whitespace Handling

Whitespace inside delimiters is ignored:

```yaml
# These are all equivalent
- ${{ inputs.name }}
- ${{inputs.name}}
- ${{  inputs.name  }}
```

</div>

<div v-click class="mt-4">

## Case Sensitivity

Identifiers are case-sensitive:

```yaml
# These are DIFFERENT
- ${{ inputs.Name }}
- ${{ inputs.name }}
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Expression Types

| Type | Syntax | Example |
|------|--------|---------|
| Input | `inputs.x` | `${{ inputs.name }}` |
| Step | `steps.x.output` | `${{ steps.greet.output }}` |
| Item | `item` | `${{ item.field }}` |
| Index | `index` | `${{ index }}` |

</div>

<div v-click class="mt-4">

## Access Patterns

Both dot and bracket notation supported:

```yaml
# Dot notation (preferred)
${{ inputs.user.name }}

# Bracket notation (for special chars/indices)
${{ inputs.user['first-name'] }}
${{ steps.fetch.output[0] }}
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Maverick Convention</strong><br>
  Use dot notation for simple paths, bracket notation 
  for array indices and keys with special characters.
</div>

</div>

<!--
The ${{ }} syntax was chosen for familiarity - it's used by GitHub Actions,
many CI/CD systems, and template engines. The expression content itself
follows a Python-like syntax with some restrictions.
-->

---
layout: two-cols
---

# 13.3 Input References

<div class="pr-4">

<div v-click>

## Basic Input Access

Reference workflow inputs defined in `inputs:` section:

```yaml
inputs:
  name:
    type: string
    required: true
  count:
    type: integer
    default: 1

steps:
  - name: process
    type: python
    action: process_data
    args:
      - ${{ inputs.name }}
      - ${{ inputs.count }}
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Nested Input Access

Inputs can be complex objects:

```yaml
inputs:
  config:
    type: object
    properties:
      timeout: { type: integer }
      retries: { type: integer }

steps:
  - name: call_api
    args:
      timeout: ${{ inputs.config.timeout }}
      retries: ${{ inputs.config.retries }}
```

</div>

<div v-click class="mt-4">

## What Happens at Runtime

```python
# Expression: ${{ inputs.name }}
# Context: {"inputs": {"name": "Alice"}}

evaluator = ExpressionEvaluator(
    inputs={"name": "Alice"},
    step_outputs={},
)
result = evaluator.evaluate(expr)  # "Alice"
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Error Handling</strong><br>
  Accessing undefined inputs raises <code>ExpressionEvaluationError</code>
  with helpful context about available variables.
</div>

</div>

<!--
Input references are the simplest expression type. They're resolved by
looking up values in the inputs dictionary passed to the workflow executor.
-->

---
layout: two-cols
---

# 13.4 Step Output References

<div class="pr-4">

<div v-click>

## Referencing Previous Steps

Access outputs from completed steps:

```yaml
steps:
  - name: analyze
    type: agent
    agent: code_analyzer
    
  - name: report
    type: python
    action: generate_report
    args:
      # Reference analyze step's output
      - ${{ steps.analyze.output }}
```

</div>

<div v-click class="mt-4">

## Syntax Pattern

```text
steps.<step_name>.output[.<field>]*
       │           │        │
       │           │        └─ Optional nested access
       │           └─ Required keyword
       └─ Step name from YAML
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Nested Field Access

Step outputs are often structured objects:

```yaml
# If analyze step returns:
# {"status": "success", "findings": [...]}

steps:
  - name: check_status
    condition: ${{ steps.analyze.output.status }}
    
  - name: process_findings
    args:
      items: ${{ steps.analyze.output.findings }}
      count: ${{ steps.analyze.output.findings[0] }}
```

</div>

<div v-click class="mt-4">

## Step Resolution

```python
# Context built during execution:
step_outputs = {
    "analyze": {
        "output": {
            "status": "success",
            "findings": ["issue1", "issue2"]
        }
    }
}

# ${{ steps.analyze.output.status }}
# Resolves to: "success"
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Step Dependencies</strong><br>
  Expressions create implicit dependencies - steps referencing 
  outputs from other steps must run after them.
</div>

</div>

<!--
Step references are crucial for workflow data flow. The executor tracks
step outputs and makes them available to subsequent steps.
-->

---
layout: two-cols
---

# 13.5 Iteration Context

<div class="pr-4">

<div v-click>

## Loop Variables: `item` and `index`

Available inside `for_each` loops:

```yaml
steps:
  - name: process_files
    type: loop
    for_each: ${{ inputs.files }}
    steps:
      - name: process_single
        type: python
        action: process_file
        args:
          - ${{ item }}       # Current element
          - ${{ index }}      # Current index (0-based)
```

</div>

<div v-click class="mt-4">

## Item as Object

When iterating over objects:

```yaml
# If inputs.users = [
#   {"name": "Alice", "role": "admin"},
#   {"name": "Bob", "role": "user"}
# ]

for_each: ${{ inputs.users }}
steps:
  - args:
      name: ${{ item.name }}
      role: ${{ item.role }}
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Runtime Binding

```python
# The evaluator receives iteration context:
evaluator = ExpressionEvaluator(
    inputs={...},
    step_outputs={...},
    iteration_context={
        "item": {"name": "Alice", "role": "admin"},
        "index": 0
    }
)

# ${{ item.name }} → "Alice"
# ${{ index }} → 0
```

</div>

<div v-click class="mt-4">

## Scope Rules

- `item` and `index` only available inside loops
- Using them outside loops raises an error:

```python
ExpressionEvaluationError(
    "Item reference used outside of for_each loop",
    expression="${{ item }}",
    context_vars=("inputs.files",)
)
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Nested Loops</strong><br>
  In nested loops, <code>item</code> and <code>index</code> refer to 
  the innermost loop. Use subworkflows for complex nesting.
</div>

</div>

<!--
Iteration context is dynamically bound as the loop executes. The evaluator
is recreated for each iteration with updated item and index values.
-->

---
layout: two-cols
---

# 13.6 Boolean Operations

<div class="pr-4">

<div v-click>

## Negation with `not`

Invert boolean values:

```yaml
steps:
  - name: real_run
    condition: ${{ not inputs.dry_run }}
    type: python
    action: execute_changes
```

</div>

<div v-click class="mt-4">

## Logical `and`

All operands must be truthy:

```yaml
condition: ${{ inputs.enabled and inputs.ready }}
```

<div class="text-sm text-muted mt-2">
Returns last value if all truthy, first falsy otherwise
</div>

</div>

<div v-click class="mt-4">

## Logical `or`

At least one operand must be truthy:

```yaml
# Use provided name or fall back to default
args:
  name: ${{ inputs.name or steps.detect.output }}
```

<div class="text-sm text-muted mt-2">
Returns first truthy value, or last value if all falsy
</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Operator Precedence

From highest to lowest:

| Precedence | Operator |
|------------|----------|
| 1 (highest) | `not` |
| 2 | `and` |
| 3 (lowest) | `or` |

```yaml
# Equivalent to: (not a) and b or c
${{ not inputs.a and inputs.b or inputs.c }}

# Use explicit grouping for clarity:
# (Currently not supported - use multiple steps)
```

</div>

<div v-click class="mt-4">

## Python-Style Short-Circuit

```python
# ${{ inputs.x or steps.y.output }}
# Evaluates to:
#   - inputs.x if truthy
#   - steps.y.output otherwise

# This allows fallback patterns without
# raising errors on the first operand
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Note</strong><br>
  Boolean expressions return actual values, not just 
  <code>True</code>/<code>False</code>. This enables 
  default value patterns.
</div>

</div>

<!--
The boolean operators use Python semantics for short-circuit evaluation.
This is important for the 'or' pattern where we want to return the actual
value, not just a boolean.
-->

---
layout: two-cols
---

# 13.7 Ternary Expressions

<div class="pr-4">

<div v-click>

## Inline Conditionals

Select between values based on a condition:

```yaml
# Syntax: value_if_true if condition else value_if_false

steps:
  - name: set_title
    args:
      title: ${{ inputs.title if inputs.title else "Untitled" }}
```

<div class="text-sm text-muted mt-2">
  Note: The order is <code>true_val if cond else false_val</code> 
  (Python style), not <code>cond ? true : false</code> (C style)
</div>

</div>

<div v-click class="mt-4">

## Common Use Cases

```yaml
# Default values
timeout: ${{ inputs.timeout if inputs.timeout else 30 }}

# Conditional arguments
mode: ${{ "fast" if inputs.quick else "thorough" }}

# Fallback to step output
name: ${{ inputs.name if inputs.name else steps.detect.output }}
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Short-Circuit Evaluation

Only the selected branch is evaluated:

```python
# Expression:
# ${{ inputs.a if inputs.flag else steps.slow.output }}

# If inputs.flag is True:
#   - inputs.a is evaluated
#   - steps.slow.output is NOT evaluated

# If inputs.flag is False:
#   - inputs.a is NOT evaluated  
#   - steps.slow.output is evaluated
```

</div>

<div v-click class="mt-4">

## Implementation

```python
def _evaluate_ternary(self, expr: TernaryExpression) -> Any:
    """Evaluate a ternary conditional expression."""
    condition_result = self.evaluate(expr.condition)
    if condition_result:
        return self.evaluate(expr.value_if_true)
    else:
        return self.evaluate(expr.value_if_false)
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Nesting</strong><br>
  Ternary expressions can be nested (right-associative), 
  but prefer separate steps for complex logic.
</div>

</div>

<!--
Ternary expressions are evaluated with short-circuit semantics - only the
branch that's selected gets evaluated. This is important for performance
and to avoid errors from evaluating unused branches.
-->

---
layout: two-cols
---

# 13.8 Template Strings

<div class="pr-4">

<div v-click>

## Mixing Literals and Expressions

Embed expressions anywhere in strings:

```yaml
steps:
  - name: log_message
    args:
      message: "Hello ${{ inputs.name }}, welcome!"
      
  - name: build_path
    args:
      path: "/data/${{ inputs.env }}/${{ inputs.file }}"
```

</div>

<div v-click class="mt-4">

## Multiple Expressions

A single string can contain many expressions:

```yaml
args:
  summary: |
    Processing ${{ inputs.count }} items
    for user ${{ inputs.user }}
    in environment ${{ inputs.env }}
```

</div>

<div v-click class="mt-4">

## Type Conversion

Non-string values are converted via `str()`:

```yaml
# If inputs.count = 42 (integer)
message: "Count: ${{ inputs.count }}"
# Result: "Count: 42"
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## The `evaluate_string` Method

```python
def evaluate_string(self, text: str) -> str:
    """Evaluate all expressions in a text string."""
    # Extract all ${{ ... }} expressions
    expressions = extract_all(text)
    
    if not expressions:
        return text  # No expressions, return as-is
    
    # Build replacement map
    replacements = {}
    for expr in expressions:
        if expr.raw not in replacements:
            value = self.evaluate(expr)
            replacements[expr.raw] = str(value)
    
    # Perform replacements
    result = text
    for expr_raw, value_str in replacements.items():
        result = result.replace(expr_raw, value_str)
    
    return result
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Pure Expressions</strong><br>
  If a value is <code>${{ expr }}</code> with no surrounding text, 
  the evaluator returns the raw value (not stringified). This 
  preserves types for non-string arguments.
</div>

</div>

<!--
Template string evaluation finds all expressions in the string, evaluates
each one, and replaces them with the string representation of the result.
The distinction between template strings and pure expressions is important
for preserving types.
-->

---
layout: two-cols
---

# 13.9 The Lark Grammar

<div class="pr-4">

<div v-click>

## Grammar Structure

```lark {all|1-3|5-7|9-12|14-17|all}
// Entry point
start: ternary_expr

// Ternary (lowest precedence)
?ternary_expr: bool_expr
    | bool_expr "if" bool_expr "else" ternary_expr

// Boolean operators
?bool_expr: bool_term (_OR bool_term)*
?bool_term: unary_expr (_AND unary_expr)*
?unary_expr: negation unary_expr -> negated_expr
           | reference

// Reference types
reference: input_ref | step_ref | item_ref | index_ref
input_ref: "inputs" accessor+
step_ref: "steps" "." IDENTIFIER "." "output" accessor*
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Access Patterns

```lark
// Item and index (for loops)
item_ref: "item" accessor*
index_ref: "index"

// Dot or bracket access
accessor: dot_accessor | bracket_accessor
dot_accessor: "." IDENTIFIER
bracket_accessor: "[" bracket_content "]"
bracket_content: INT | STRING

// Terminals
IDENTIFIER: /[a-zA-Z_][a-zA-Z0-9_]*/
INT: /-?[0-9]+/
STRING: /'[^']*'/ | /"[^"]*"/
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Grammar Benefits</strong><br>
  <ul class="list-disc ml-4 mt-1 text-xs">
    <li>Single source of truth for syntax</li>
    <li>Automatic error position tracking</li>
    <li>Extensible without rewriting parser</li>
    <li>Documentation and implementation in sync</li>
  </ul>
</div>

<div v-click class="mt-3 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">File Location</strong><br>
  <code>src/maverick/dsl/expressions/grammar.lark</code>
</div>

</div>

<!--
The grammar file is the formal specification of the expression language.
The LALR parser generated from this grammar handles all the complexity
of precedence, associativity, and error reporting.
-->

---
layout: two-cols
---

# 13.10 Parser Implementation

<div class="pr-4">

<div v-click>

## Core Data Structures

```python
class ExpressionKind(str, Enum):
    """Kind of expression reference."""
    INPUT_REF = "input_ref"   # inputs.x
    STEP_REF = "step_ref"     # steps.x.output
    ITEM_REF = "item_ref"     # item
    INDEX_REF = "index_ref"   # index


@dataclass(frozen=True, slots=True)
class Expression:
    raw: str              # Original string
    kind: ExpressionKind  # Reference type
    path: tuple[str, ...]  # Access path
    negated: bool = False  # Wrapped in 'not'
```

</div>

<div v-click class="mt-4">

## Compound Expressions

```python
@dataclass(frozen=True, slots=True)
class BooleanExpression:
    raw: str
    operator: Literal["and", "or"]
    operands: tuple[AnyExpression, ...]


@dataclass(frozen=True, slots=True)
class TernaryExpression:
    raw: str
    condition: AnyExpression
    value_if_true: AnyExpression
    value_if_false: AnyExpression
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## The Transformer

```python
class _ExpressionTransformer(Transformer):
    """Transform parse tree → Expression objects."""
    
    def input_ref(self, items: list[str]) -> Expression:
        return Expression(
            raw=self._raw,
            kind=ExpressionKind.INPUT_REF,
            path=tuple(["inputs"] + list(items)),
            negated=False,
        )
    
    def step_ref(self, items: list[str]) -> Expression:
        path = ["steps", str(items[0]), "output"]
        path.extend(str(x) for x in items[1:])
        return Expression(
            raw=self._raw,
            kind=ExpressionKind.STEP_REF,
            path=tuple(path),
            negated=False,
        )
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Immutable by Design</strong><br>
  Expression objects are frozen dataclasses with slots - 
  lightweight, hashable, and safe to pass around.
</div>

</div>

<!--
The parser transforms the raw text into structured Expression objects.
The Transformer class walks the parse tree and builds the appropriate
expression type based on the grammar rules matched.
-->

---
layout: two-cols
---

# 13.11 Evaluator Implementation

<div class="pr-4">

<div v-click>

## ExpressionEvaluator Class

```python
class ExpressionEvaluator:
    """Evaluates expressions against context."""
    
    def __init__(
        self,
        inputs: dict[str, Any],
        step_outputs: dict[str, Any],
        iteration_context: dict[str, Any] | None = None,
    ) -> None:
        self._inputs = inputs
        self._step_outputs = step_outputs
        self._iteration_context = iteration_context or {}
```

</div>

<div v-click class="mt-4">

## Path Navigation

```python
def evaluate(self, expr: AnyExpression) -> Any:
    # Determine root based on kind
    if expr.kind == ExpressionKind.INPUT_REF:
        root = self._inputs
    elif expr.kind == ExpressionKind.STEP_REF:
        root = self._step_outputs
    # ... item_ref, index_ref
    
    # Navigate path
    current = root
    for key in expr.path[1:]:  # Skip root name
        current = current[key]  # or [int(key)]
    
    return not current if expr.negated else current
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Error Handling

```python
# Helpful error messages with context
if key not in current:
    available = self._get_available_keys(root, root_name)
    raise ExpressionEvaluationError(
        f"Input '{key}' not found",
        expression=expr.raw,
        context_vars=available,  # ("inputs.name", "inputs.count")
    )
```

</div>

<div v-click class="mt-4">

## Access Pattern Support

The evaluator handles multiple access patterns:

| Pattern | Example | Code |
|---------|---------|------|
| Dict | `inputs.name` | `current[key]` |
| List | `output[0]` | `current[int(key)]` |
| String | `name[0]` | `current[int(key)]` |
| Object | `obj.attr` | `getattr(current, key)` |

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">File Location</strong><br>
  <code>src/maverick/dsl/expressions/evaluator.py</code>
</div>

</div>

<!--
The evaluator is the runtime component that resolves expressions to values.
It supports multiple access patterns and provides helpful error messages
when paths can't be resolved.
-->

---
layout: center
class: text-center
---

# Expression System Summary

<div class="grid grid-cols-3 gap-6 mt-8 max-w-4xl mx-auto">

<div v-click class="p-4 rounded-lg bg-teal/10 border border-teal/30">
  <div class="text-3xl mb-2">📝</div>
  <div class="font-bold text-teal">Grammar</div>
  <div class="text-sm text-muted mt-2">
    Lark-based EBNF grammar defines syntax rules
  </div>
  <div class="text-xs mt-2 font-mono bg-slate-800 rounded p-1">
    grammar.lark
  </div>
</div>

<div v-click class="p-4 rounded-lg bg-brass/10 border border-brass/30">
  <div class="text-3xl mb-2">🔍</div>
  <div class="font-bold text-brass">Parser</div>
  <div class="text-sm text-muted mt-2">
    Transforms text into typed Expression objects
  </div>
  <div class="text-xs mt-2 font-mono bg-slate-800 rounded p-1">
    parser.py
  </div>
</div>

<div v-click class="p-4 rounded-lg bg-coral/10 border border-coral/30">
  <div class="text-3xl mb-2">⚡</div>
  <div class="font-bold text-coral">Evaluator</div>
  <div class="text-sm text-muted mt-2">
    Resolves expressions against runtime context
  </div>
  <div class="text-xs mt-2 font-mono bg-slate-800 rounded p-1">
    evaluator.py
  </div>
</div>

</div>

<div v-click class="mt-8">

## Key Design Decisions

<div class="flex justify-center gap-4 text-sm mt-4">
  <span class="px-3 py-1 rounded bg-slate-700">Python-style ternary</span>
  <span class="px-3 py-1 rounded bg-slate-700">Short-circuit evaluation</span>
  <span class="px-3 py-1 rounded bg-slate-700">Immutable AST nodes</span>
  <span class="px-3 py-1 rounded bg-slate-700">Typed error messages</span>
</div>

</div>

<div v-click class="mt-6 text-sm text-muted">
  Next: Step Execution Framework - how workflows execute step by step
</div>

<!--
The expression system is a complete mini-language embedded in Maverick workflows.
The clean separation between grammar, parser, and evaluator makes it easy to
extend with new features while maintaining correctness.
-->
