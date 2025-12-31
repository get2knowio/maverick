---
name: maverick-rust-clippy
description: Rust Clippy lints and common fixes
version: 1.0.0
triggers:
  - clippy
  - "#[allow(clippy"
  - lint
  - warning
---

# Rust Clippy Skill

## Must-Fix Lints

### clippy::redundant_clone
```rust
// BAD
let s = String::from("hello");
let s2 = s.clone();
drop(s);  // s never used again

// GOOD
let s = String::from("hello");
let s2 = s;  // Move instead of clone
```

### clippy::needless_borrow
```rust
// BAD
foo(&mut &mut x);

// GOOD
foo(&mut x);
```

### clippy::large_enum_variant
Box large enum variants to reduce enum size.

## Review Severity
- **MAJOR**: redundant_clone, needless_borrow
- **MINOR**: Most other Clippy warnings
- **SUGGESTION**: Could simplify with Clippy suggestion
