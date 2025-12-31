# Performance Tests

This directory contains performance tests and benchmarks for critical Maverick components.

## Test Suite

### Discovery Performance Tests (`test_discovery_performance.py`)

Validates that workflow discovery meets the performance requirement from T064:
- **Requirement**: Discovery must complete in under 500ms for 100 workflow files
- **Status**: ✅ All tests pass (7-13x faster than required)

#### Test Cases

1. **test_discovery_performance_100_workflows**
   - Creates 100 minimal workflow YAML files in a flat structure
   - Measures discovery time and validates < 500ms requirement
   - **Result**: ~55ms (89% under requirement)

2. **test_discovery_performance_with_fragments**
   - Tests mixed content: 50 workflows + 50 fragments
   - Validates fragment discovery doesn't impact performance
   - **Result**: ~38ms (92% under requirement)

3. **test_discovery_performance_with_nested_directories**
   - Tests 100 workflows across 10 nested subdirectories
   - Validates recursive glob performance
   - **Result**: ~37ms (93% under requirement)

4. **test_discovery_performance_benchmark_200_workflows**
   - Benchmark test with 200 workflows to verify scaling
   - Marked with `@pytest.mark.benchmark` (may be skipped in CI)
   - **Result**: ~73ms (linear scaling, 0.37ms per workflow)

## Running Tests

```bash
# Run all performance tests
PYTHONPATH=src python -m pytest tests/performance/ -v

# Run with performance output
PYTHONPATH=src python -m pytest tests/performance/ -v -s

# Run specific test
PYTHONPATH=src python -m pytest tests/performance/test_discovery_performance.py::TestDiscoveryPerformance::test_discovery_performance_100_workflows -v

# Skip benchmark tests
PYTHONPATH=src python -m pytest tests/performance/ -v -m "not benchmark"
```

## Performance Analysis

See [PERFORMANCE_ANALYSIS.md](./PERFORMANCE_ANALYSIS.md) for detailed analysis including:
- Test results summary
- Scaling characteristics
- Implementation analysis
- Potential bottlenecks
- Optimization recommendations

## Adding New Performance Tests

When adding new performance tests:

1. **Document the requirement**: Include the performance requirement as a comment
2. **Measure and report**: Print performance metrics for debugging
3. **Assert the requirement**: Use clear assertion messages with actual vs. required times
4. **Test scaling**: Include at least one test at 2x the requirement to verify scaling
5. **Use fixtures**: Leverage pytest fixtures (`temp_dir`, `monkeypatch`) for isolation

Example:
```python
def test_my_performance(self, temp_dir: Path) -> None:
    """Test my feature completes in under Xms.

    Performance requirement: < Xms (TXXX)
    """
    # Setup
    # ... create test data ...

    # Measure
    start = time.perf_counter()
    result = my_function()
    duration_ms = (time.perf_counter() - start) * 1000

    # Assert
    assert duration_ms < X, f"Took {duration_ms:.2f}ms, requirement is < {X}ms"

    # Report
    print(f"\\nPerformance: {duration_ms:.2f}ms")
```

## CI Integration

Performance tests run in CI as part of the standard test suite. Tests are designed to:
- Pass reliably on CI infrastructure (with headroom for slower machines)
- Complete quickly (< 5 seconds total for all performance tests)
- Provide actionable failure messages with actual vs. required times

## Benchmarking

For more detailed performance profiling, use Python's profiling tools:

```bash
# Profile with cProfile
python -m cProfile -o profile.stats -m pytest tests/performance/test_discovery_performance.py

# Analyze with snakeviz
pip install snakeviz
snakeviz profile.stats

# Or use pytest-benchmark for statistical analysis
pip install pytest-benchmark
pytest tests/performance/ --benchmark-only
```
