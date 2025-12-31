---
name: maverick-python-testing
description: Python testing best practices with pytest, unittest, and mocking
version: 1.0.0
triggers:
  - pytest
  - unittest
  - test_
  - "@pytest.fixture"
  - "@fixture"
  - "@mock"
  - "@patch"
  - conftest.py
  - "test_*.py"
  - assert
  - parametrize
  - mock
---

# Python Testing Skill

Expert guidance for Python testing with pytest, unittest, fixtures, and mocking patterns.

## Pytest Best Practices

### Test Structure
- Name tests `test_*.py` or `*_test.py`
- Use fixtures for test setup (avoid `setUp`/`tearDown`)
- Group related tests in classes (optional, for organization)
- One assertion per test (or closely related assertions)

**Example:**
```python
import pytest

@pytest.fixture
def sample_data():
    """Fixture providing test data."""
    return {"key": "value"}

def test_function_with_fixture(sample_data):
    """Test using fixture data."""
    result = process(sample_data)
    assert result == expected_value
```

### Fixtures

**Scope Levels:**
- `function` (default) - Per test function
- `class` - Per test class
- `module` - Per test module
- `session` - Per test session

**Example:**
```python
@pytest.fixture(scope="module")
def database():
    """Module-scoped database fixture."""
    db = Database()
    db.connect()
    yield db
    db.disconnect()

@pytest.fixture
def user(database):
    """Function-scoped user (depends on database)."""
    user = database.create_user("test@example.com")
    yield user
    database.delete_user(user.id)
```

### Parametrize for Multiple Cases

**Single Parameter:**
```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_double(input, expected):
    assert double(input) == expected
```

**Multiple Parameters:**
```python
@pytest.mark.parametrize("username", ["alice", "bob"])
@pytest.mark.parametrize("role", ["admin", "user"])
def test_permissions(username, role):
    """Runs 4 tests (2x2 combinations)."""
    user = User(username, role)
    assert user.has_role(role)
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await async_operation()
    assert result == expected
```

## Mocking Patterns

### unittest.mock

**Patch Decorator:**
```python
from unittest.mock import patch, MagicMock

@patch('module.external_api_call')
def test_with_mock(mock_api):
    mock_api.return_value = {"status": "ok"}

    result = function_that_calls_api()

    mock_api.assert_called_once_with(expected_args)
    assert result == expected
```

**Patch Context Manager:**
```python
def test_with_context_manager():
    with patch('module.function') as mock_func:
        mock_func.return_value = 42
        assert call_function() == 42
```

**Mock Attributes:**
```python
mock = MagicMock()
mock.method.return_value = "result"
mock.attribute = "value"

# Assertions
mock.method.assert_called()
mock.method.assert_called_with(arg1, arg2)
mock.method.assert_called_once()
assert mock.method.call_count == 3
```

### Common Mocking Mistakes

**WRONG - Patching in wrong place:**
```python
# File: myapp/module.py
from external import api_call

def my_function():
    return api_call()

# File: tests/test_module.py
# WRONG - patches external.api_call, not myapp.module.api_call
@patch('external.api_call')
def test_wrong(mock_api):
    my_function()  # Doesn't use the mock!
```

**CORRECT:**
```python
# CORRECT - patch where it's used, not where it's defined
@patch('myapp.module.api_call')
def test_correct(mock_api):
    my_function()  # Uses the mock
```

## Test Coverage

### Aim for Meaningful Coverage
- **Target**: >80% coverage for critical code
- Test edge cases (empty lists, None, zero, negative numbers)
- Test error conditions (exceptions, invalid input)
- Don't test framework code or trivial getters/setters

### Run Coverage
```bash
pytest --cov=myapp --cov-report=html tests/
```

### Coverage Configuration
```ini
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "--cov=src --cov-report=term-missing"
```

## Test Organization

### Directory Structure
```
project/
├── src/
│   └── myapp/
│       ├── __init__.py
│       └── module.py
└── tests/
    ├── conftest.py           # Shared fixtures
    ├── unit/
    │   └── test_module.py
    └── integration/
        └── test_workflow.py
```

### conftest.py for Shared Fixtures
```python
# tests/conftest.py
import pytest

@pytest.fixture(scope="session")
def app_config():
    """Application configuration for all tests."""
    return {"debug": True, "db": ":memory:"}

@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file for testing."""
    file = tmp_path / "test.txt"
    file.write_text("test content")
    return file
```

## Common Testing Patterns

### Testing Exceptions
```python
import pytest

def test_raises_exception():
    with pytest.raises(ValueError, match="invalid input"):
        function_that_raises("bad")
```

### Testing Warnings
```python
import warnings
import pytest

def test_warning():
    with pytest.warns(DeprecationWarning):
        legacy_function()
```

### Testing Async Generators
```python
@pytest.mark.asyncio
async def test_async_generator():
    gen = async_generator()
    items = [item async for item in gen]
    assert len(items) == 3
```

### Testing with Temporary Files
```python
def test_file_processing(tmp_path):
    """pytest provides tmp_path fixture."""
    test_file = tmp_path / "input.txt"
    test_file.write_text("test data")

    process_file(test_file)

    output = (tmp_path / "output.txt").read_text()
    assert output == "processed: test data"
```

## Markers for Test Organization

```python
import pytest

@pytest.mark.slow
def test_slow_operation():
    """Mark slow tests to skip in quick runs."""
    pass

@pytest.mark.integration
def test_database_integration():
    """Mark integration tests separately."""
    pass

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    pass

@pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
def test_unix_specific():
    pass

@pytest.mark.xfail(reason="Known bug #123")
def test_known_issue():
    pass
```

**Run specific markers:**
```bash
pytest -m "not slow"           # Skip slow tests
pytest -m integration          # Only integration tests
```

## Antipatterns to Avoid

### ❌ Testing Implementation Details
```python
# BAD - tests internal implementation
def test_cache_uses_dict():
    cache = Cache()
    assert isinstance(cache._storage, dict)

# GOOD - tests behavior
def test_cache_retrieval():
    cache = Cache()
    cache.set("key", "value")
    assert cache.get("key") == "value"
```

### ❌ Unclear Test Names
```python
# BAD
def test_user():
    pass

# GOOD
def test_user_creation_with_valid_email():
    pass
```

### ❌ Multiple Unrelated Assertions
```python
# BAD - tests multiple unrelated things
def test_everything():
    assert func1() == 1
    assert func2() == 2
    assert func3() == 3

# GOOD - separate tests
def test_func1_returns_one():
    assert func1() == 1

def test_func2_returns_two():
    assert func2() == 2
```

### ❌ Test Interdependencies
```python
# BAD - tests depend on execution order
def test_create_user():
    global user_id
    user_id = create_user("alice")

def test_get_user():
    user = get_user(user_id)  # Depends on previous test!

# GOOD - use fixtures for setup
@pytest.fixture
def user_id():
    return create_user("alice")

def test_get_user(user_id):
    user = get_user(user_id)
```

## Review Severity Guidelines

- **CRITICAL**: No tests for new code, tests disabled/skipped without justification
- **MAJOR**: Missing edge case tests, testing implementation details, test interdependencies
- **MINOR**: Missing docstrings on tests, inconsistent naming
- **SUGGESTION**: Could use parametrize for similar tests, opportunity for shared fixture

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
