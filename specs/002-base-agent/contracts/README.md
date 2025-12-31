# Contracts: Base Agent Abstraction Layer

**Feature**: 002-base-agent | **Date**: 2025-12-12

## Overview

This directory contains the API contracts for the base agent abstraction layer. Since this is an internal Python library (not a REST/GraphQL API), contracts are defined as Python Protocols.

## Files

| File | Description |
|------|-------------|
| `agent_protocol.py` | Protocol definitions for all public interfaces |

## Contracts Summary

### Data Contracts

| Protocol | Purpose | FR Reference |
|----------|---------|--------------|
| `AgentUsageProtocol` | Usage statistics structure | FR-014 |
| `AgentResultProtocol` | Execution result structure | FR-008 |
| `AgentContextProtocol` | Runtime context structure | FR-009 |

### Service Contracts

| Protocol | Purpose | FR Reference |
|----------|---------|--------------|
| `AgentProtocol` | Base agent interface | FR-001, FR-004, FR-005 |
| `AgentRegistryProtocol` | Agent discovery/instantiation | FR-010, FR-011, FR-012 |
| `TextExtractorProtocol` | Utility functions | FR-006 |

## Usage in Tests

These protocols can be used for type checking and creating test doubles:

```python
from contracts.agent_protocol import AgentProtocol, AgentResultProtocol

class MockAgent:
    """Test double implementing AgentProtocol."""

    def __init__(self, name: str = "mock"):
        self._name = name
        self._system_prompt = "Mock agent"
        self._allowed_tools: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    # ... implement other protocol methods

# Type checking
agent: AgentProtocol = MockAgent()
assert isinstance(agent, AgentProtocol)  # True with @runtime_checkable
```

## Versioning

Contract changes follow semantic versioning:
- **MAJOR**: Breaking changes to protocol signatures
- **MINOR**: New methods added with defaults
- **PATCH**: Documentation updates only
