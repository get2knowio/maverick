"""Tests for CheckpointData dataclass."""

from __future__ import annotations

from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash


class TestCheckpointData:
    """Tests for CheckpointData class."""

    # T074: CheckpointData serialization/deserialization
    def test_to_dict_and_from_dict(self) -> None:
        """CheckpointData should serialize and deserialize correctly."""
        # Create a CheckpointData instance with all fields
        data = CheckpointData(
            checkpoint_id="step1",
            workflow_name="my_workflow",
            inputs_hash="abcd1234efgh5678",
            step_results=(
                {"name": "step1", "success": True, "output": "result1"},
                {"name": "step2", "success": False, "error": "failure"},
            ),
            saved_at="2024-01-01T00:00:00Z",
        )

        # Call to_dict() and verify the structure
        d = data.to_dict()
        assert d["checkpoint_id"] == "step1"
        assert d["workflow_name"] == "my_workflow"
        assert d["inputs_hash"] == "abcd1234efgh5678"
        assert d["step_results"] == [
            {"name": "step1", "success": True, "output": "result1"},
            {"name": "step2", "success": False, "error": "failure"},
        ]
        assert d["saved_at"] == "2024-01-01T00:00:00Z"
        assert isinstance(d["step_results"], list)

        # Call from_dict() to recreate and verify equality
        restored = CheckpointData.from_dict(d)
        assert restored == data
        assert restored.checkpoint_id == data.checkpoint_id
        assert restored.workflow_name == data.workflow_name
        assert restored.inputs_hash == data.inputs_hash
        assert restored.step_results == data.step_results
        assert restored.saved_at == data.saved_at
        assert isinstance(restored.step_results, tuple)

    # T075: compute_inputs_hash determinism
    def test_compute_inputs_hash_determinism(self) -> None:
        """Same inputs should produce same hash."""
        inputs = {"key": "value", "number": 42, "nested": {"a": 1, "b": 2}}

        # Call compute_inputs_hash with identical dicts multiple times
        h1 = compute_inputs_hash(inputs)
        h2 = compute_inputs_hash(inputs)
        h3 = compute_inputs_hash(inputs)

        # Verify all hashes are equal
        assert h1 == h2
        assert h2 == h3

        # Verify hash format (16-char hex string)
        assert len(h1) == 16
        assert all(c in "0123456789abcdef" for c in h1)

    def test_compute_inputs_hash_different_inputs(self) -> None:
        """Different inputs should produce different hashes."""
        # Create two different input dicts
        inputs1 = {"key": "value1", "number": 42}
        inputs2 = {"key": "value2", "number": 42}

        # Compute hashes for both
        hash1 = compute_inputs_hash(inputs1)
        hash2 = compute_inputs_hash(inputs2)

        # Verify hashes are different
        assert hash1 != hash2

        # Verify both are valid hex strings of correct length
        assert len(hash1) == 16
        assert len(hash2) == 16
        assert all(c in "0123456789abcdef" for c in hash1)
        assert all(c in "0123456789abcdef" for c in hash2)

    def test_compute_inputs_hash_non_serializable_raises(self) -> None:
        """Non-JSON-serializable inputs should raise TypeError (lines 33-34)."""
        import pytest

        # Create inputs with a non-JSON-serializable object
        class CustomObject:
            pass

        inputs = {"key": "value", "obj": CustomObject()}

        with pytest.raises(TypeError, match="JSON-serializable"):
            compute_inputs_hash(inputs)
