---
name: maverick-python-async
description: Python async/await patterns and asyncio best practices
version: 1.0.0
triggers:
  - async def
  - await
  - asyncio
  - async with
  - async for
  - coroutine
  - Task
  - gather
  - create_task
  - aiohttp
  - aiofiles
---

# Python Async/Await Skill

Expert guidance for asynchronous Python programming with asyncio.

## Core Concepts

### Async Functions (Coroutines)
```python
async def fetch_data(url: str) -> dict:
    """Async function returns a coroutine."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```

### Running Async Code
```python
import asyncio

# Python 3.7+
asyncio.run(main())

# Or event loop (older style)
loop = asyncio.get_event_loop()
loop.run_until_complete(main())
```

## Common Patterns

### Concurrent Execution
```python
# gather - run concurrently, wait for all
results = await asyncio.gather(
    fetch_data(url1),
    fetch_data(url2),
    fetch_data(url3),
)

# create_task - run in background
task1 = asyncio.create_task(fetch_data(url1))
task2 = asyncio.create_task(fetch_data(url2))
result1 = await task1
result2 = await task2
```

### Timeouts
```python
try:
    result = await asyncio.wait_for(
        slow_operation(),
        timeout=5.0
    )
except asyncio.TimeoutError:
    print("Operation timed out")
```

### Async Context Managers
```python
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.text()
```

### Async Iterators
```python
async for item in async_generator():
    process(item)
```

## Antipatterns

### ❌ Blocking Calls in Async Functions
```python
# BAD - blocks event loop
async def bad():
    time.sleep(1)  # BLOCKS!
    response = requests.get(url)  # BLOCKS!

# GOOD - use async alternatives
async def good():
    await asyncio.sleep(1)
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
```

### ❌ Not Awaiting Coroutines
```python
# BAD - coroutine never executes
async def bad():
    fetch_data()  # Missing await!

# GOOD
async def good():
    await fetch_data()
```

### ❌ Creating Too Many Tasks
```python
# BAD - creates 10000 tasks at once
tasks = [asyncio.create_task(fetch(url)) for url in urls]

# GOOD - use semaphore to limit concurrency
async def fetch_with_limit(url, semaphore):
    async with semaphore:
        return await fetch(url)

semaphore = asyncio.Semaphore(10)
tasks = [fetch_with_limit(url, semaphore) for url in urls]
```

## Review Severity

- **CRITICAL**: Blocking calls in async functions (time.sleep, requests.get)
- **MAJOR**: Missing await on coroutines, not handling asyncio.CancelledError
- **MINOR**: Not using async context managers, inefficient gather usage
