# Maverick DSL Expression Grammar

This document provides a formal specification of the Maverick DSL expression language used in `${{ ... }}` template expressions throughout workflow definitions.

## Table of Contents

- [Overview](#overview)
- [BNF Grammar](#bnf-grammar)
- [Operator Precedence](#operator-precedence)
- [Expression Semantics](#expression-semantics)
- [Variable Resolution](#variable-resolution)
- [Type Coercion](#type-coercion)
- [Error Handling](#error-handling)
- [Examples](#examples)

## Overview

Maverick workflow expressions enable dynamic value substitution and conditional logic in YAML workflow definitions. Expressions are enclosed in `${{ ... }}` delimiters and can reference workflow inputs, step outputs, and iteration variables.

### Key Features

- **Variable References**: Access inputs, step outputs, and loop variables
- **Boolean Logic**: Combine conditions with `and`, `or`, and `not` operators
- **Ternary Conditionals**: Inline value selection based on conditions
- **Nested Access**: Navigate object properties and array indices
- **Strong Validation**: Early detection of syntax errors with precise error positions

## BNF Grammar

The grammar is defined using Extended Backus-Naur Form (EBNF). The implementation uses the [Lark parser](https://lark-parser.readthedocs.io/) with this grammar.

### Complete Grammar

```ebnf
(* Entry point *)
<start> ::= <ternary-expr>

(* Ternary conditional - lowest precedence, right-associative *)
<ternary-expr> ::= <bool-expr>
                 | <bool-expr> "if" <bool-expr> "else" <ternary-expr>

(* Boolean expressions - 'or' has lower precedence than 'and' *)
<bool-expr> ::= <bool-term> ("or" <bool-term>)*

<bool-term> ::= <unary-expr> ("and" <unary-expr>)*

(* Unary expressions - negation with 'not' *)
<unary-expr> ::= "not" <unary-expr>
               | <reference>

(* Reference types - determines ExpressionKind *)
<reference> ::= <input-ref>
              | <step-ref>
              | <item-ref>
              | <index-ref>

(* Input reference: inputs.name, inputs.config.value *)
<input-ref> ::= "inputs" <accessor>+

(* Step reference: steps.step_id.output[.field]* *)
<step-ref> ::= "steps" "." <identifier> "." "output" <accessor>*

(* Item reference: item, item.field, item[0] *)
<item-ref> ::= "item" <accessor>*

(* Index reference: index (no nested access allowed) *)
<index-ref> ::= "index"

(* Accessor patterns - dot notation or bracket notation *)
<accessor> ::= <dot-accessor>
             | <bracket-accessor>

<dot-accessor> ::= "." <identifier>

<bracket-accessor> ::= "[" <bracket-content> "]"

<bracket-content> ::= <integer>
                    | <string>

(* Terminals *)
<identifier> ::= /[a-zA-Z_][a-zA-Z0-9_]*/
<integer> ::= /-?[0-9]+/
<string> ::= /'[^']*'/ | /"[^"]*"/

(* Whitespace is ignored between tokens *)
```

### Grammar Notes

1. **Right-Associativity of Ternary**: The ternary operator is right-associative, meaning `a if b else c if d else e` is parsed as `a if b else (c if d else e)`.

2. **No Double Negation**: The grammar allows `not not x` syntactically, but the parser explicitly rejects it with a validation error.

3. **Index Restrictions**: The `index` reference cannot have nested accessors. This is enforced both by grammar and validation.

4. **Required 'output' Keyword**: Step references must include `.output` between the step ID and any field accessors. This is enforced by the grammar.

5. **Minimum Path Requirements**:
   - Input references require at least one accessor: `inputs.name` (not just `inputs`)
   - Step references require step ID and output: `steps.x.output` (not just `steps.x`)

## Operator Precedence

Operators are listed from lowest to highest precedence:

| Precedence | Operator | Associativity | Description |
|------------|----------|---------------|-------------|
| 1 (lowest) | `if...else` | Right | Ternary conditional |
| 2 | `or` | Left | Boolean OR |
| 3 | `and` | Left | Boolean AND |
| 4 (highest) | `not` | Right | Boolean negation |

### Precedence Examples

```python
# 'and' binds tighter than 'or'
${{ a or b and c }}
# Parsed as: a or (b and c)

# 'not' binds tighter than 'and'
${{ not a and b }}
# Parsed as: (not a) and b

# Ternary has lowest precedence
${{ a if b and c else d }}
# Parsed as: a if (b and c) else d

# Right-associative ternary
${{ a if b else c if d else e }}
# Parsed as: a if b else (c if d else e)
```

## Expression Semantics

### Operators

#### Negation (`not`)

Inverts the boolean value of an expression.

- **Syntax**: `not <expr>`
- **Returns**: Boolean
- **Examples**:
  - `not inputs.skip_tests` - True if input is falsy
  - `not steps.check.output` - True if step output is falsy

**Important**: Double negation (`not not x`) is explicitly disallowed.

#### Boolean AND (`and`)

Evaluates to true if all operands are truthy.

- **Syntax**: `<expr> and <expr> [and <expr>]*`
- **Short-circuit evaluation**: Stops at first falsy operand
- **Returns**: Boolean
- **Examples**:
  - `inputs.enabled and inputs.validated`
  - `steps.a.output and steps.b.output and steps.c.output`

#### Boolean OR (`or`)

Evaluates to true if any operand is truthy.

- **Syntax**: `<expr> or <expr> [or <expr>]*`
- **Short-circuit evaluation**: Stops at first truthy operand
- **Returns**: Boolean
- **Examples**:
  - `inputs.use_cache or inputs.force_rebuild`
  - `steps.a.output or steps.b.output or inputs.default`

#### Ternary Conditional (`if...else`)

Selects a value based on a condition.

- **Syntax**: `<value_if_true> if <condition> else <value_if_false>`
- **Returns**: The type of the selected branch
- **Examples**:
  - `inputs.title if inputs.title else steps.generate_title.output`
  - `"enabled" if inputs.flag else "disabled"`

### Accessor Patterns

#### Dot Notation

Accesses object properties by name.

- **Syntax**: `.<identifier>`
- **Examples**:
  - `inputs.config.database.host`
  - `steps.api_call.output.data.user.email`

#### Bracket Notation

Accesses array elements or object properties using indices or string keys.

- **Syntax**: `[<index>]` or `[<key>]`
- **Integer index**: `item[0]`, `item[-1]` (negative indices supported)
- **String key**: `item['key']`, `item["key"]`
- **Examples**:
  - `steps.list_files.output[0]` - First element
  - `item['name']` - Property access with string key
  - `steps.results.output.data[2].value` - Combined access

## Variable Resolution

Expressions can reference four types of variables, resolved in this order within their scope:

### 1. Workflow Inputs (`inputs`)

Variables passed when starting the workflow.

- **Scope**: Available throughout entire workflow
- **Syntax**: `inputs.<name>[.field]*`
- **Examples**:
  - `${{ inputs.repository_name }}`
  - `${{ inputs.config.timeout }}`

### 2. Step Outputs (`steps`)

Results from previously executed steps.

- **Scope**: Available after the step completes
- **Syntax**: `steps.<step_id>.output[.field]*`
- **Required keyword**: `.output` must appear between step ID and fields
- **Examples**:
  - `${{ steps.build.output }}`
  - `${{ steps.api_call.output.data.items }}`

### 3. Iteration Item (`item`)

Current item in a `for_each` loop.

- **Scope**: Available only within the for_each step
- **Syntax**: `item[.field]*` or `item[index]`
- **Examples**:
  - `${{ item }}` - The entire item
  - `${{ item.name }}` - Field access
  - `${{ item[0] }}` - Array element

### 4. Iteration Index (`index`)

Current iteration index in a `for_each` loop (0-based).

- **Scope**: Available only within the for_each step
- **Syntax**: `index` (no nested access)
- **Restriction**: Cannot use accessors with index
- **Examples**:
  - `${{ index }}` - Valid
  - `${{ index.field }}` - **Invalid**: Index cannot have accessors

### Resolution Rules

1. **Scope-based resolution**: Variables are only accessible in their defined scope
2. **No shadowing**: Variable names don't conflict (inputs, steps, item, index are distinct namespaces)
3. **Undefined references**: Accessing undefined variables raises `ExpressionEvaluationError` at runtime
4. **Type safety**: The grammar ensures syntactically valid references; type checking happens at evaluation time

## Type Coercion

The expression language follows Python's truthiness rules:

### Truthy Values

- Non-empty strings: `"text"`, `"0"`
- Non-zero numbers: `1`, `-1`, `3.14`
- Non-empty collections: `[1, 2]`, `{"key": "value"}`
- Boolean true: `true`

### Falsy Values

- Empty string: `""`
- Zero: `0`, `0.0`
- Empty collections: `[]`, `{}`
- Null/None: `null`
- Boolean false: `false`

### Boolean Context

All expressions in boolean contexts (`not`, `and`, `or`, ternary condition) are coerced to boolean using truthiness rules.

```yaml
# Example: Empty string is falsy
when: ${{ inputs.title }}  # False if title is ""

# Example: Non-zero number is truthy
when: ${{ steps.count.output }}  # True if count is non-zero
```

## Error Handling

The parser provides detailed error messages with position information for syntax errors.

### Common Syntax Errors

#### 1. Empty Expression

```
Error: Empty expression
Expression: ${{ }}
```

#### 2. Invalid Prefix

```
Error: Expression must start with 'inputs', 'steps', 'item', or 'index', got 'outputs'
Expression: outputs.name
                ^
```

#### 3. Missing 'output' in Step Reference

```
Error: Step reference must include 'output' (e.g., steps.x.output)
Expression: steps.x.result
                    ^
```

#### 4. Index with Accessor

```
Error: Index reference must be a single element (e.g., ${{ index }})
Expression: index.field
                 ^
```

#### 5. Double Negation

```
Error: Double negation is not allowed
Expression: not not inputs.flag
```

#### 6. Trailing Dot

```
Error: Expression cannot end with a dot
Expression: inputs.name.
                       ^
```

#### 7. Invalid Character

```
Error: Invalid character '-' in expression at position 9
Expression: inputs.my-name
                     ^
```

### Error Position Indicators

All syntax errors include:
- **Position**: Character offset where error occurred
- **Visual indicator**: Caret (^) pointing to the error location
- **Helpful message**: Explanation of what went wrong and how to fix it

## Examples

### Basic References

```yaml
# Input reference
name: ${{ inputs.repository_name }}

# Step output reference
result: ${{ steps.build.output }}

# Nested field access
email: ${{ steps.api_call.output.data.user.email }}

# Array index access
first_item: ${{ steps.fetch_list.output.items[0] }}
```

### Boolean Logic

```yaml
# Simple negation
when: ${{ not inputs.skip_tests }}

# AND condition
when: ${{ inputs.enabled and inputs.validated }}

# OR condition
when: ${{ inputs.use_cache or inputs.force_rebuild }}

# Complex boolean expression
when: ${{ inputs.enabled and (steps.check.output or inputs.force) }}
```

### Ternary Conditionals

```yaml
# Simple ternary
title: ${{ inputs.title if inputs.title else steps.generate_title.output }}

# With negation
mode: ${{ "production" if not inputs.debug else "development" }}

# Nested ternary (right-associative)
level: ${{ "high" if inputs.critical else "medium" if inputs.important else "low" }}

# With boolean operators in condition
value: ${{ inputs.a if inputs.b and inputs.c else inputs.default }}
```

### Iteration Variables

```yaml
# In for_each loop
for_each:
  items: ${{ steps.get_files.output }}
  steps:
    - id: process
      python:
        action: process_file
        args:
          filename: ${{ item.name }}
          index: ${{ index }}
          is_first: ${{ not index }}
```

### Complex Real-World Examples

```yaml
# Conditional step execution based on multiple factors
when: ${{ inputs.enabled and not inputs.dry_run and steps.validate.output.success }}

# Dynamic branch name with fallback
branch_name: ${{ inputs.branch if inputs.branch else "fix/issue-${{ inputs.issue_number }}" }}

# Nested data access with conditional
api_url: ${{ steps.config.output.api.endpoints.production if inputs.production else steps.config.output.api.endpoints.staging }}

# Array processing with item and index
for_each:
  items: ${{ steps.fetch_issues.output.issues }}
  steps:
    - id: process_issue
      when: ${{ item.state == "open" and not item.locked }}
      python:
        action: process_issue
        args:
          issue: ${{ item }}
          position: ${{ index }}
```

## Implementation Notes

### Parser Technology

The grammar is implemented using [Lark](https://lark-parser.readthedocs.io/), a modern parsing toolkit for Python:

- **Parser Algorithm**: LALR (Look-Ahead Left-to-Right)
- **Grammar File**: `src/maverick/dsl/expressions/grammar.lark`
- **Parser Module**: `src/maverick/dsl/expressions/parser.py`

### Design Decisions

1. **No Arithmetic Operators**: The DSL is intentionally limited to boolean logic and conditionals. Arithmetic should be performed in Python actions.

2. **No Comparison Operators**: Expressions like `x == y` or `x > 5` are not supported. Use Python actions for comparisons.

3. **No Function Calls**: No built-in functions (like `len()`, `upper()`, etc.). All transformations happen in Python actions.

4. **Explicit 'output' Keyword**: Step references require `.output` to make data flow explicit and prevent confusion.

5. **Index Accessor Restriction**: `index` cannot have nested fields because it's an integer, not an object. This prevents confusing errors.

### Performance Characteristics

- **Parse Time**: O(n) where n is expression length
- **Memory**: Minimal - expressions are parsed once and cached
- **Error Reporting**: O(1) position tracking with zero-copy string slicing

## Grammar Evolution

This grammar is stable but may be extended in future versions. Backward compatibility is maintained for all valid expressions.

### Potential Future Extensions

- Comparison operators: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Arithmetic operators: `+`, `-`, `*`, `/`, `%`
- String operations: Concatenation, interpolation
- Built-in functions: `len()`, `upper()`, `lower()`, etc.
- Null-coalescing operator: `??`

Any extensions will follow these principles:
1. Backward compatibility with existing expressions
2. Clear, unambiguous syntax
3. Comprehensive error messages
4. Full test coverage

## References

- **Parser Implementation**: `src/maverick/dsl/expressions/parser.py`
- **Grammar File**: `src/maverick/dsl/expressions/grammar.lark`
- **Test Suite**: `tests/unit/dsl/expressions/test_parser.py`
- **Error Types**: `src/maverick/dsl/expressions/errors.py`
- **Lark Documentation**: https://lark-parser.readthedocs.io/
