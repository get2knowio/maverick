---
layout: section
class: text-center
---

# 8. Tenacity - Retry Logic

<div class="text-lg text-secondary mt-4">
Resilient operations with exponential backoff
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">8 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Exponential Backoff</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Async-Native</span>
  </div>
</div>

<!--
Section 8 covers Tenacity - the library that powers all retry logic in Maverick.

We'll cover:
1. Why retry logic matters
2. Tenacity overview and concepts
3. Basic retry decorator
4. Wait strategies (fixed, exponential, random)
5. Stop conditions
6. Retry conditions (exception types, result checking)
7. AsyncRetrying for async code
8. Real Maverick examples
-->

---

## layout: two-cols

# 8.1 Why Retry?

<div class="pr-4">

**Transient failures are everywhere** in distributed systems

<div v-click class="mt-4">

## Common Failure Scenarios

<div class="space-y-3 text-sm mt-3">

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">◆</span>
  <div>
    <strong>Network Issues</strong>
    <div class="text-muted">Connection timeouts, DNS failures, TCP resets</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">◆</span>
  <div>
    <strong>Rate Limiting</strong>
    <div class="text-muted">GitHub: 5000/hr, Claude API: requests/min</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">◆</span>
  <div>
    <strong>Resource Contention</strong>
    <div class="text-muted">Git lock files, database locks, file system</div>
  </div>
</div>

<div class="flex items-start gap-2">
  <span class="text-coral font-bold">◆</span>
  <div>
    <strong>Service Availability</strong>
    <div class="text-muted">Temporary outages, deployments, scaling events</div>
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
# Manual retry - DON'T DO THIS
def push_changes():
    for attempt in range(3):
        try:
            return git_push()
        except GitError:
            if attempt == 2:
                raise
            time.sleep(attempt * 2)  # Ad-hoc backoff
```

<div class="text-xs text-muted mt-2">
Problems: No jitter, hard-coded values, verbose, error-prone
</div>

</div>

<div v-click class="mt-4">

## The Tenacity Way ✓

```python
from tenacity import retry, stop_after_attempt

@retry(stop=stop_after_attempt(3))
def push_changes():
    return git_push()  # Clean, declarative!
```

<div class="text-xs text-muted mt-2">
Clean, configurable, well-tested, supports async
</div>

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Maverick Rule:</strong> Never write manual retry loops. Always use Tenacity's <code>@retry</code> decorator or <code>AsyncRetrying</code> context manager.
</div>

</div>

<!--
Why do we need retry logic at all?

**Transient Failures**: These are failures that go away if you try again. Networks hiccup, services restart, rate limits reset. In distributed systems, they're not the exception - they're the rule.

**The Wrong Way**: You might be tempted to write a for loop with try/except. But this has problems:
- No jitter (random variation) leads to thundering herd
- Hard-coded values scattered everywhere
- Easy to get the logic wrong
- Doesn't compose with async code

**The Tenacity Way**: Declarative retry logic. Specify WHAT you want (3 attempts), not HOW to implement it. Tenacity handles the sleep, the exception catching, and supports both sync and async.

**Maverick Rule**: This is non-negotiable. Manual retry loops are technical debt.
-->

---

## layout: default

# 8.2 Tenacity Overview

<div class="text-secondary text-sm mb-4">
Declarative retry logic for Python
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Installation

```bash
# Already included in Maverick
uv sync

# Or install directly
pip install tenacity
```

</div>

<div v-click class="mt-4">

### Core Concepts

<div class="space-y-2 text-sm">

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">@retry</code>
  <div class="text-muted text-xs mt-1">Decorator for retryable functions</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">stop_*</code>
  <div class="text-muted text-xs mt-1">When to give up (attempts, time)</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">wait_*</code>
  <div class="text-muted text-xs mt-1">How long between retries</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">retry_if_*</code>
  <div class="text-muted text-xs mt-1">What conditions trigger retry</div>
</div>

<div class="p-2 rounded border border-slate-300 dark:border-slate-700">
  <code class="text-teal">AsyncRetrying</code>
  <div class="text-muted text-xs mt-1">Context manager for async code</div>
</div>

</div>

</div>

</div>

<div>

<div v-click>

### Basic Example

```python {1-5|7-9|11-15|all}
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
)
def fetch_data():
    """Fetches data with retry on any exception."""
    response = requests.get(API_URL)
    response.raise_for_status()
    return response.json()
```

</div>

<div v-click class="mt-4">

### How It Works

```text
Attempt 1 → Exception → Wait 1s
Attempt 2 → Exception → Wait 2s
Attempt 3 → Exception → Raise (stop)
         or
Attempt 3 → Success   → Return value
```

</div>

</div>

</div>

<!--
Let's understand Tenacity's core concepts.

**@retry Decorator**: The main way to add retry logic. Decorate a function and configure the retry behavior.

**stop_* functions**: Define when to stop retrying. By attempts, by total time, or combine them.

**wait_* functions**: Define how long to wait between retries. Fixed, exponential, random, or custom.

**retry_if_* functions**: Define WHAT triggers a retry. Specific exception types, return value checking, or custom predicates.

**AsyncRetrying**: For async code where you need more control, use this context manager instead of the decorator.

The example shows a typical pattern: retry up to 3 times with exponential backoff starting at 1 second, capped at 10 seconds.
-->

---

## layout: default

# 8.3 Basic Retry

<div class="text-secondary text-sm mb-4">
The <code>@retry</code> decorator fundamentals
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Simplest Form

```python
from tenacity import retry

@retry  # Retries forever on any exception!
def might_fail():
    return risky_operation()
```

<div class="mt-2 p-2 bg-coral/10 border border-coral/30 rounded text-xs">
  ⚠️ <strong>Warning:</strong> Without <code>stop</code>, this retries indefinitely!
</div>

</div>

<div v-click class="mt-4">

### With Stop Condition

```python
from tenacity import retry, stop_after_attempt

@retry(stop=stop_after_attempt(3))
def might_fail():
    """Try up to 3 times, then give up."""
    return risky_operation()
```

</div>

<div v-click class="mt-4">

### Stop After Time

```python
from tenacity import retry, stop_after_delay

@retry(stop=stop_after_delay(30))  # 30 seconds max
def might_fail():
    """Keep trying for up to 30 seconds."""
    return risky_operation()
```

</div>

</div>

<div>

<div v-click>

### Combining Stop Conditions

```python
from tenacity import retry, stop_after_attempt, stop_after_delay

@retry(
    stop=(
        stop_after_attempt(5) |  # Max 5 tries
        stop_after_delay(60)     # OR 60 seconds
    )
)
def might_fail():
    """Stop on whichever comes first."""
    return risky_operation()
```

</div>

<div v-click class="mt-4">

### Re-raising the Exception

```python
from tenacity import retry, stop_after_attempt

@retry(
    stop=stop_after_attempt(3),
    reraise=True  # Re-raise original exception
)
def might_fail():
    return risky_operation()

# Without reraise=True, raises RetryError
# With reraise=True, raises the original exception
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Best Practice:</strong> Always specify <code>stop</code> and set <code>reraise=True</code> for better error messages and debugging.
</div>

</div>

</div>

<!--
Let's look at the @retry decorator in detail.

**Simplest Form**: Just `@retry` with no arguments. DANGEROUS! This retries forever. Never use this in production.

**stop_after_attempt**: The most common stop condition. Specify maximum number of attempts.

**stop_after_delay**: Stop after a certain amount of time has passed. Useful for time-sensitive operations.

**Combining Stops**: Use `|` (or) to combine stop conditions. Stop when EITHER condition is met.

**reraise=True**: By default, Tenacity wraps the exception in a `RetryError`. Set `reraise=True` to get the original exception, which is better for debugging and error handling downstream.

**Maverick Pattern**: We always set both `stop` and `reraise=True` for predictable behavior.
-->

---

## layout: two-cols

# 8.4 Wait Strategies

<div class="pr-4">

How long to pause between retries

<div v-click class="mt-4">

### Fixed Wait

```python
from tenacity import retry, wait_fixed

@retry(wait=wait_fixed(2))  # Always 2 seconds
def api_call():
    return make_request()
```

<div class="text-xs text-muted mt-1">
Simple but can cause "thundering herd" if many clients retry simultaneously
</div>

</div>

<div v-click class="mt-4">

### Exponential Backoff

```python
from tenacity import retry, wait_exponential

@retry(
    wait=wait_exponential(
        multiplier=1,  # Base multiplier
        min=1,         # Minimum wait: 1 second
        max=60         # Maximum wait: 60 seconds
    )
)
def api_call():
    return make_request()
```

```text
Attempt 1 → fail → wait 1s
Attempt 2 → fail → wait 2s
Attempt 3 → fail → wait 4s
Attempt 4 → fail → wait 8s
...capped at 60s...
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click>

### Random Wait

```python
from tenacity import retry, wait_random

@retry(wait=wait_random(min=1, max=5))
def api_call():
    """Wait random 1-5 seconds."""
    return make_request()
```

</div>

<div v-click class="mt-4">

### Exponential + Random (Jitter)

```python
from tenacity import (
    retry,
    wait_exponential,
    wait_random,
)

@retry(
    wait=wait_exponential(multiplier=1, max=30)
          + wait_random(0, 2)  # Add 0-2s jitter
)
def api_call():
    """Exponential backoff with jitter."""
    return make_request()
```

<div class="text-xs text-muted mt-1">
Jitter prevents synchronized retries from overwhelming servers
</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Maverick Pattern:</strong>
  <code class="text-xs block mt-1">wait_exponential(multiplier=1, min=1, max=10)</code>
  <div class="text-xs mt-1">Used for all network operations (git push, GitHub API)</div>
</div>

<div v-click class="mt-4">

### Wait Chain

```python
# Wait 5s, 10s, 30s, then 60s forever
wait=wait_chain(
    wait_fixed(5),
    wait_fixed(10),
    wait_fixed(30),
    wait_fixed(60)
)
```

</div>

</div>

<!--
Wait strategies control the delay between retry attempts.

**wait_fixed**: Simple constant delay. Easy to understand but problematic at scale - if 1000 clients fail at the same time, they all retry at the same time.

**wait_exponential**: Doubles the wait time on each attempt. This is the gold standard for distributed systems. Backed-off clients don't overwhelm the recovering service.

Parameters:
- multiplier: Scales the base time
- min/max: Clamps the wait time

**wait_random**: Adds randomness. Good for spreading out retries.

**Exponential + Random (Jitter)**: The best of both worlds. Exponential backoff with random jitter to prevent synchronized retries. Use `+` to combine wait strategies.

**Maverick's Pattern**: We use `wait_exponential(multiplier=1, min=1, max=10)` for network operations. Fast initial retry (1s), reasonable maximum (10s).

**wait_chain**: Advanced - specify exact delays for each attempt.
-->

---

## layout: default

# 8.5 Stop Conditions

<div class="text-secondary text-sm mb-4">
When to give up and propagate the failure
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### By Attempt Count

```python
from tenacity import stop_after_attempt

# Stop after 3 attempts (original + 2 retries)
stop=stop_after_attempt(3)
```

</div>

<div v-click class="mt-4">

### By Total Time

```python
from tenacity import stop_after_delay

# Stop after 30 seconds total
stop=stop_after_delay(30)
```

</div>

<div v-click class="mt-4">

### Combining with OR

```python
from tenacity import stop_after_attempt, stop_after_delay

# Stop after 5 attempts OR 60 seconds
stop=(stop_after_attempt(5) | stop_after_delay(60))
```

</div>

<div v-click class="mt-4">

### Combining with AND

```python
# Stop only when BOTH conditions met
# (rarely used, but possible)
stop=(stop_after_attempt(10) & stop_after_delay(60))
```

</div>

</div>

<div>

<div v-click>

### Never Stop (Dangerous!)

```python
from tenacity import stop_never

# Retries forever - use with caution!
stop=stop_never
```

<div class="mt-2 p-2 bg-coral/10 border border-coral/30 rounded text-xs">
  ⚠️ Only use with external timeout or circuit breaker
</div>

</div>

<div v-click class="mt-4">

### Custom Stop Condition

```python
from tenacity import stop_base

class stop_after_business_hours(stop_base):
    """Stop if outside business hours."""

    def __call__(self, retry_state):
        hour = datetime.now().hour
        return hour < 9 or hour > 17
```

</div>

<div v-click class="mt-4">

### Maverick's Network Constants

```python
# src/maverick/git/repository.py

#: Maximum retries for network operations
MAX_NETWORK_RETRIES: int = 3

#: Default timeout for network operations
DEFAULT_NETWORK_TIMEOUT: float = 60.0
```

<div class="mt-2 p-3 bg-teal/10 border border-teal/30 rounded-lg text-xs">
  Constants defined once, used consistently across the codebase
</div>

</div>

</div>

</div>

<!--
Stop conditions determine when to give up retrying.

**stop_after_attempt**: Most common. Specify the maximum number of attempts. Note: 3 attempts means original call + 2 retries.

**stop_after_delay**: Time-based. Good for operations with SLAs - "I need this to complete within 30 seconds or fail."

**Combining with |**: OR logic - stop when EITHER condition is met. This is the common pattern for production code.

**Combining with &**: AND logic - stop only when BOTH conditions are met. Rarely used but available.

**stop_never**: Retries indefinitely. Only use this when you have external timeout handling (like an async task with timeout wrapper).

**Custom Stop**: You can create your own stop conditions by inheriting from `stop_base`. The `__call__` method receives a `retry_state` object with attempt information.

**Maverick Constants**: We define constants like `MAX_NETWORK_RETRIES = 3` once and use them everywhere. No magic numbers in retry decorators.
-->

---

## layout: two-cols

# 8.6 Retry Conditions

<div class="pr-4">

Controlling WHAT triggers a retry

<div v-click class="mt-4">

### Retry on Specific Exceptions

```python
from tenacity import retry, retry_if_exception_type

@retry(
    retry=retry_if_exception_type(ConnectionError)
)
def fetch():
    return requests.get(url)
```

<div class="text-xs text-muted mt-1">
Only retries ConnectionError; other exceptions propagate immediately
</div>

</div>

<div v-click class="mt-4">

### Multiple Exception Types

```python
from tenacity import retry, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((
        ConnectionError,
        TimeoutError,
        OSError,
    ))
)
def fetch():
    return requests.get(url)
```

</div>

<div v-click class="mt-4">

### Retry on Result Value

```python
from tenacity import retry, retry_if_result

@retry(
    retry=retry_if_result(lambda x: x is None)
)
def fetch_until_ready():
    """Retry while result is None."""
    return check_status()
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click>

### Custom Retry Predicate

```python
from tenacity import retry, retry_if_exception

def is_retryable_git_error(exc):
    """Check if git error is network-related."""
    if not isinstance(exc, GitCommandError):
        return False
    stderr = str(exc.stderr or "").lower()
    patterns = [
        "could not resolve host",
        "connection refused",
        "connection timed out",
        "network unreachable",
        "unable to access",
    ]
    return any(p in stderr for p in patterns)

@retry(
    retry=retry_if_exception(is_retryable_git_error)
)
def git_push():
    return repo.remote().push()
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Maverick Pattern:</strong> Pattern-match on error messages to identify transient failures. Don't retry permanent errors like "permission denied".
</div>

</div>

<!--
Retry conditions control WHAT triggers a retry.

**retry_if_exception_type**: Only retry specific exception types. This is important - you don't want to retry on ValueError (programmer error) or PermissionError (won't succeed).

**Multiple Types**: Pass a tuple of exception types to retry on any of them.

**retry_if_result**: Retry based on the return value. Useful for polling patterns where the function returns None until ready.

**Custom Predicate**: For complex logic, write a function that examines the exception. Maverick uses this for git errors - we check the error message to distinguish network errors (retry) from permission errors (don't retry).

**Key Insight**: The retry predicate is where domain knowledge lives. Git's "could not resolve host" is transient (retry). Git's "permission denied" is permanent (don't retry). Tenacity gives you the tools; you provide the judgment.
-->

---

## layout: default

# 8.7 AsyncRetrying

<div class="text-secondary text-sm mb-4">
Context manager for async operations
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Why Not Just @retry?

```python
# This works but has limitations
@retry(stop=stop_after_attempt(3))
async def fetch():
    return await client.get(url)
```

<div class="text-xs text-muted mt-1">
Decorator works for async, but context manager gives more control
</div>

</div>

<div v-click class="mt-4">

### AsyncRetrying Pattern

```python {1-5|7-16|18-22|all}
from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_exponential,
)

async def fetch_with_retry():
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    ):
        with attempt:
            result = await client.get(url)
            return result.json()
    # Never reached if reraise=True

# Can access attempt info inside loop
async for attempt in AsyncRetrying(...):
    with attempt:
        print(f"Attempt {attempt.retry_state.attempt_number}")
        return await risky_operation()
```

</div>

</div>

<div>

<div v-click>

### Maverick's CommandRunner

```python {1-6|8-18|20-30|all}
# From src/maverick/runners/command.py
from tenacity import (
    AsyncRetrying,
    stop_after_attempt,
    wait_exponential,
)

async def run(
    self,
    command: Sequence[str],
    max_retries: int = 0,
    retry_delay: float = 1.0,
) -> CommandResult:
    """Execute command with optional retry."""

    last_result: CommandResult | None = None

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(
                multiplier=retry_delay,
                min=retry_delay,
                max=60
            ),
            reraise=True,
        ):
            with attempt:
                result = await self._execute_once(command)

                if result.success:
                    return result

                if not self.is_retryable(result):
                    return result

                # Raise to trigger retry
                raise RetryableCommandError(result)
```

</div>

</div>

</div>

<!--
AsyncRetrying is the async context manager form of Tenacity.

**Why Use It?**
- More control over what happens in each attempt
- Access to attempt state (attempt number, elapsed time)
- Conditional retry based on result (not just exceptions)
- Cleaner integration with async code patterns

**The Pattern**: `async for attempt in AsyncRetrying(...):` gives you an iterator. Inside the `with attempt:` block, your code runs. If it raises, Tenacity checks whether to retry.

**Maverick's CommandRunner**: This is real production code. We use AsyncRetrying because:
1. We need to check the result (success vs retryable error vs permanent error)
2. We want to return the result even on non-retryable failure
3. We need exponential backoff with configurable initial delay

**Key Detail**: We raise `RetryableCommandError` to signal "retry this". If we just return, the loop ends. The `with attempt:` context manager catches exceptions and decides whether to retry.
-->

---

## layout: two-cols

# 8.8 Maverick Examples

<div class="pr-4">

Real-world patterns from the codebase

<div v-click class="mt-4">

### Git Network Retry Decorator

```python
# src/maverick/git/repository.py

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from git import GitCommandError

#: Maximum retries for network operations
MAX_NETWORK_RETRIES: int = 3

# Reusable decorator for network ops
network_retry = retry(
    retry=retry_if_exception_type(GitCommandError),
    stop=stop_after_attempt(MAX_NETWORK_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
```

</div>

<div v-click class="mt-4">

### Using the Decorator

```python
class AsyncGitRepository:
    """Git operations with retry."""

    @network_retry
    async def push(self, ...) -> None:
        """Push with automatic retry."""
        await asyncio.to_thread(
            self._repo.remote().push, ...
        )

    @network_retry
    async def pull(self, ...) -> None:
        """Pull with automatic retry."""
        await asyncio.to_thread(
            self._repo.remote().pull, ...
        )
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click>

### Network Error Detection

```python
# Pattern matching for retryable errors
def _is_network_error(exc: BaseException) -> bool:
    """Check if error is network-related."""
    if not isinstance(exc, GitCommandError):
        return False
    stderr = str(exc.stderr or "").lower()
    network_patterns = [
        "could not resolve host",
        "connection refused",
        "connection timed out",
        "network unreachable",
        "temporary failure",
        "unable to access",
        "ssl",
        "tls",
    ]
    return any(p in stderr for p in network_patterns)
```

</div>

<div v-click class="mt-4">

### CommandRunner Retryable Check

```python
# src/maverick/runners/command.py

def is_retryable(self, result: CommandResult) -> bool:
    """Determine if failure should be retried."""
    # Retry on timeout
    if result.timed_out:
        return True

    # Retry on connection reset
    if "connection reset" in result.stderr.lower():
        return True

    # Retry on rate limit
    return "rate limit" in result.stderr.lower()
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Key Insight:</strong> Retry conditions encode domain knowledge about what failures are transient vs permanent.
</div>

</div>

<!--
Let's look at how Maverick actually uses Tenacity.

**Reusable Decorator**: We define `network_retry` once with all the configuration. Then we apply it to any method that does network I/O. DRY principle in action.

**Applied to Methods**: `push()`, `pull()`, `fetch()` all get the same retry behavior automatically. If we need to change the retry policy, we change it in one place.

**Network Error Detection**: This function embodies our domain knowledge. We know these specific error messages indicate transient network issues. We explicitly check for these patterns rather than blindly retrying all GitCommandErrors.

**CommandRunner**: The runner checks results for retryable conditions - timeouts, connection resets, rate limits. These are infrastructure-level transient failures that affect any external command.

**The Insight**: Tenacity provides the retry machinery. Your code provides the domain knowledge about WHAT to retry. This separation is clean and maintainable.
-->

---

## layout: center

class: text-center

# Tenacity Cheat Sheet

<div class="grid grid-cols-3 gap-4 max-w-5xl mx-auto mt-8 text-sm">

<div v-click class="p-4 border border-slate-300 dark:border-slate-700 rounded-lg text-left">

### Stop Conditions

```python
stop_after_attempt(3)
stop_after_delay(60)
stop_never

# Combine with | (or)
stop_after_attempt(5) | stop_after_delay(120)
```

</div>

<div v-click class="p-4 border border-slate-300 dark:border-slate-700 rounded-lg text-left">

### Wait Strategies

```python
wait_fixed(2)
wait_exponential(multiplier=1, max=60)
wait_random(min=1, max=5)

# Combine with + (add)
wait_exponential(...) + wait_random(0, 2)
```

</div>

<div v-click class="p-4 border border-slate-300 dark:border-slate-700 rounded-lg text-left">

### Retry Conditions

```python
retry_if_exception_type(ValueError)
retry_if_result(lambda x: x is None)
retry_if_exception(predicate_fn)

# Default: retry on any exception
```

</div>

</div>

<div v-click class="mt-8 p-4 bg-brass/10 border border-brass/30 rounded-lg max-w-2xl mx-auto">

### Maverick's Standard Pattern

```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

@retry(
    retry=retry_if_exception_type(SpecificError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def reliable_operation():
    ...
```

</div>

<div v-click class="mt-6 text-muted text-sm">
Full docs: <a href="https://tenacity.readthedocs.io/" target="_blank" class="text-teal hover:underline">tenacity.readthedocs.io</a>
</div>

<!--
Here's your quick reference for Tenacity.

**Stop Conditions**: Use `stop_after_attempt` for most cases. Combine with `|` for "OR" logic.

**Wait Strategies**: `wait_exponential` is the gold standard. Add `wait_random` for jitter to prevent thundering herd.

**Retry Conditions**: Always specify what to retry on. Don't retry everything - only transient failures.

**Maverick's Pattern**: This is our standard template. Specific exception type, 3 attempts, exponential backoff 1-10 seconds, reraise for clean error handling.

Bookmark the Tenacity docs - there's more advanced features like callbacks, logging hooks, and statistics we didn't cover.
-->
