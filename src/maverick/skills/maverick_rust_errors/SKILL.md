---
name: maverick-rust-errors
description: Rust error handling with Result, Error trait, anyhow, thiserror
version: 1.0.0
triggers:
  - Result
  - "?"
  - Error
  - anyhow
  - thiserror
  - unwrap
  - expect
  - "Result<"
---

# Rust Errors Skill

## Result Type
```rust
fn parse_number(s: &str) -> Result<i32, ParseIntError> {
    s.parse()
}

// Use ? operator for propagation
fn process() -> Result<(), Error> {
    let num = parse_number("42")?;
    Ok(())
}
```

## Custom Errors with thiserror
```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum MyError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Parse error: {0}")]
    Parse(String),
}
```

## Avoid unwrap/expect in Production
```rust
// BAD
let value = some_option.unwrap();

// GOOD
let value = some_option.ok_or(MyError::MissingValue)?;

// OR provide default
let value = some_option.unwrap_or_default();
```

## Review Severity
- **CRITICAL**: unwrap/expect without justification
- **MAJOR**: Missing error handling
- **MINOR**: Could use ? operator
