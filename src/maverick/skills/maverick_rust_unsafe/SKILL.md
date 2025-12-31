---
name: maverick-rust-unsafe
description: Rust unsafe code, FFI, and safety invariants
version: 1.0.0
triggers:
  - unsafe
  - "unsafe {"
  - "unsafe fn"
  - raw pointer
  - "*const"
  - "*mut"
  - transmute
  - FFI
  - extern
---

# Rust Unsafe Skill

## When to Use Unsafe
- FFI with C libraries
- Raw pointers for performance
- Type transmutation (rare, dangerous)
- Unsafe trait implementations

## Safety Documentation
```rust
/// SAFETY: The slice is guaranteed to be non-empty by the caller.
/// This is enforced by the type system via NonEmptySlice.
unsafe fn get_first_unchecked(slice: &[i32]) -> i32 {
    debug_assert!(!slice.is_empty());
    *slice.get_unchecked(0)
}
```

## Avoid Unsafe When Possible
```rust
// BAD - unjustified unsafe
unsafe fn get_first(slice: &[i32]) -> i32 {
    *slice.get_unchecked(0)
}

// GOOD - safe alternative
fn get_first(slice: &[i32]) -> Option<&i32> {
    slice.first()
}
```

## Review Severity
- **CRITICAL**: Unsafe without justification, potential undefined behavior
- **MAJOR**: Missing safety documentation, unsafe could be safe
- **MINOR**: Debug assertions missing in unsafe code
