---
name: maverick-rust-async
description: Rust async/await with Tokio and async patterns
version: 1.0.0
triggers:
  - async fn
  - .await
  - tokio
  - async move
  - Future
  - Pin
  - Send
  - Sync
  - spawn
  - JoinHandle
---

# Rust Async Skill

## Tokio Basics
```rust
#[tokio::main]
async fn main() {
    let result = fetch_data().await;
}

async fn fetch_data() -> Result<String, Error> {
    // async operation
}
```

## Spawning Tasks
```rust
let handle = tokio::spawn(async move {
    expensive_operation().await
});

let result = handle.await?;
```

## Send + Sync Bounds
- `Send`: Can transfer across thread boundaries
- `Sync`: Can be shared across threads (&T is Send)
- Use `Arc` instead of `Rc` for thread-safe reference counting

## Review Severity
- **CRITICAL**: Blocking calls in async functions
- **MAJOR**: Using Rc in async code (not Send)
- **MINOR**: Not using async context managers
