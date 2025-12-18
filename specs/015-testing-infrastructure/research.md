# Research: Testing Infrastructure

**Feature Branch**: `015-testing-infrastructure`
**Date**: 2025-12-17
**Status**: Complete

## Overview

This document consolidates research findings for the Testing Infrastructure feature, covering four key areas: Claude Agent SDK mocking, Textual TUI testing, GitHub Actions CI configuration, and Click CLI testing.

---

## 1. Claude Agent SDK Mocking

### Decision: Response Queue with Factory Fixtures

**Rationale**: The current codebase uses ad-hoc mock setup with `sys.modules` patching. A reusable mock client with response queue provides better test maintainability and reduces boilerplate.

**Alternatives Considered**:
- Continue with inline mock setup - Rejected: Too much duplication
- Use MagicMock auto-spec - Rejected: SDK not installed in test environment
- Third-party mock libraries - Rejected: Unnecessary dependency

### Implementation Pattern

```python
class MockSDKClient:
    """Mock Claude Agent SDK client with response queue (FIFO)."""

    def __init__(self):
        self._responses: list[list[Any]] = []
        self.query_calls: list[str] = []
        self._response_index = 0

    def queue_response(self, messages: list[MockMessage]) -> None:
        """Queue a response sequence."""
        self._responses.append(messages)

    async def query(self, prompt: str) -> None:
        self.query_calls.append(prompt)

    async def receive_response(self):
        if self._response_index < len(self._responses):
            for msg in self._responses[self._response_index]:
                yield msg
            self._response_index += 1

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
```

### Message Factory Pattern

```python
class MockMessage:
    """Simplified mock message for testing."""

    def __init__(self, msg_type: str, **kwargs: Any):
        self.__class__.__name__ = msg_type
        for key, value in kwargs.items():
            setattr(self, key, value)

@pytest.fixture
def mock_text_message():
    def _create(text: str = "Response") -> MockMessage:
        return MockMessage("TextMessage", text=text)
    return _create

@pytest.fixture
def mock_result_message():
    def _create(input_tokens: int = 100, output_tokens: int = 200) -> MockMessage:
        return MockMessage("ResultMessage",
                          usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
                          total_cost_usd=0.005, duration_ms=1500)
    return _create
```

### Async Generator Testing

**Best Practice**: Use factory functions for reusable async generators with error injection support.

```python
def create_mock_receive_generator(*messages):
    """Factory for async message generators with error support."""
    async def _mock_receive():
        for msg in messages:
            if isinstance(msg, Exception):
                raise msg
            yield msg
    return _mock_receive
```

---

## 2. Textual TUI Testing with Pilot Framework

### Decision: Use `app.run_test()` Pattern with pytest-asyncio

**Rationale**: Maverick already uses this pattern extensively in `tests/unit/tui/`. The pilot framework provides a clean API for simulating user interaction.

**Alternatives Considered**:
- Direct widget instantiation testing - Rejected: Misses rendering and event handling
- Snapshot testing - Deferred: Add later for visual regression

### Setup Configuration

Existing `pyproject.toml` configuration is correct:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Key Pilot APIs

| Method | Usage |
|--------|-------|
| `await pilot.press("key")` | Simulate keyboard input |
| `await pilot.click("#selector")` | Simulate mouse click |
| `await pilot.pause()` | Wait for async operations |
| `await pilot.hover("#selector")` | Simulate mouse hover |

### Test Pattern

```python
class MyScreenTestApp(App):
    def compose(self):
        yield MyScreen()

@pytest.mark.asyncio
async def test_screen_interaction() -> None:
    async with MyScreenTestApp().run_test() as pilot:
        screen = pilot.app.screen

        # Perform action
        await pilot.click("#button")
        await pilot.pause()

        # Assert state
        assert screen.action_triggered is True
```

### Common Pitfalls to Avoid

1. **Missing `await pilot.pause()`** - Assertions run before async operations complete
2. **Incorrect selectors** - Widget IDs must match definitions
3. **Not mocking app context** - Unit tests need mocked dependencies
4. **Test state isolation** - Use fresh state per test, avoid class variables

---

## 3. GitHub Actions CI Configuration

### Decision: Matrix Build with Built-in Caching

**Rationale**: Test across Python 3.10, 3.11, 3.12 with parallel execution and pip caching for fast CI runs.

**Alternatives Considered**:
- Single Python version - Rejected: Need to verify compatibility
- External caching services - Rejected: setup-python v4 has built-in caching
- Container-based builds - Rejected: Unnecessary complexity for Python project

### Recommended Workflow Structure

```yaml
name: Test & Quality Assurance

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: "3.10"
          cache: 'pip'
          cache-dependency-path: 'pyproject.toml'
      - run: pip install -e ".[lint]"
      - run: ruff check src/ tests/

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: "3.10"
          cache: 'pip'
      - run: pip install -e ".[lint]"
      - run: mypy src/

  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: true
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      - run: pip install -e ".[test]"
      - run: pytest --cov=maverick --cov-fail-under=80 --junit-xml=results.xml
      - uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Python ${{ matrix.python-version }} Results
          path: 'results.xml'
          reporter: 'java-junit'
```

### Coverage Enforcement

- Use `pytest --cov-fail-under=80` to fail CI if coverage drops below 80%
- Generate XML coverage report for external tools
- Terminal output with `--cov-report=term-missing` shows uncovered lines

### Annotation Reporting

- Use `dorny/test-reporter` to process JUnit XML from pytest
- Annotates test failures inline in PR diffs
- Configure pytest with `--junit-xml=results.xml`

### Caching Strategy

- Built-in `cache: 'pip'` in `actions/setup-python@v4` caches pip wheels
- Cache key based on `pyproject.toml` hash
- Saves 10-20 seconds per run

---

## 4. Click CLI Testing with CliRunner

### Decision: CliRunner with Async Command Wrapper

**Rationale**: Click's CliRunner provides comprehensive CLI testing. Maverick's `@async_command` decorator bridges async workflows to synchronous Click commands.

**Alternatives Considered**:
- Direct subprocess testing - Rejected: Slow and harder to mock
- asyncclick package - Rejected: Adds dependency, current pattern works

### CliRunner Setup

```python
@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()

def test_command(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
```

### Testing Async Commands

```python
def test_async_workflow_command(cli_runner: CliRunner) -> None:
    with patch("maverick.main.FlyWorkflow") as mock_workflow_cls:
        mock_workflow = AsyncMock()
        mock_workflow_cls.return_value = mock_workflow
        mock_workflow.execute.return_value = MagicMock(success=True)

        result = cli_runner.invoke(cli, ["fly", "feature-branch"])

        assert result.exit_code == 0
        mock_workflow.execute.assert_called_once()
```

### Mocking Context Dependencies

Maverick stores dependencies in `ctx.obj`:
```python
def test_with_context_dependencies(cli_runner, temp_dir, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    os.chdir(temp_dir)

    with patch("subprocess.run") as mock_subprocess:
        mock_subprocess.return_value = MagicMock(returncode=0)
        result = cli_runner.invoke(cli, ["review", "123"])
        assert result.exit_code == 0
```

### Testing Patterns

| Pattern | Usage |
|---------|-------|
| Exit codes | `assert result.exit_code == 0` |
| Output content | `assert "success" in result.output` |
| Mocking subprocess | `patch("subprocess.run")` |
| Async workflows | `AsyncMock` for workflow methods |
| Filesystem isolation | `runner.isolated_filesystem()` |

---

## Summary of Technology Decisions

| Area | Decision | Implementation |
|------|----------|----------------|
| SDK Mocking | Response queue with factories | `MockSDKClient` class in `tests/fixtures/agents.py` |
| TUI Testing | Pilot framework with pytest-asyncio | Use `app.run_test()` pattern |
| CI Configuration | GitHub Actions with matrix builds | `.github/workflows/test.yml` |
| Coverage Threshold | 80% minimum with `--cov-fail-under` | Enforced in CI pytest command |
| Async Test Timeout | 30 seconds default | Configure in pytest settings |
| CLI Testing | CliRunner with async wrapper | Use existing `@async_command` pattern |

---

## References

- [Textual Testing Guide](https://textual.textualize.io/guide/testing/)
- [Click Testing Documentation](https://click.palletsprojects.com/en/stable/testing/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [GitHub Actions Python Guide](https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-python)
