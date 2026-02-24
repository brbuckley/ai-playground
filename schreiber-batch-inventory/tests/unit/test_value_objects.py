"""Unit tests for domain value objects."""

import pytest

from app.domain.value_objects import BatchCode, Volume


class TestBatchCode:
    """Tests for BatchCode value object."""

    def test_valid_batch_code(self):
        """Valid batch codes should be accepted."""
        bc = BatchCode("SCH-20251204-0001")
        assert bc.value == "SCH-20251204-0001"

    def test_str_returns_value(self):
        """str(BatchCode) should return the underlying string."""
        bc = BatchCode("SCH-20260101-9999")
        assert str(bc) == "SCH-20260101-9999"

    def test_equality(self):
        """Two BatchCodes with the same value should be equal."""
        bc1 = BatchCode("SCH-20251204-0001")
        bc2 = BatchCode("SCH-20251204-0001")
        assert bc1 == bc2

    def test_inequality(self):
        """BatchCodes with different values should not be equal."""
        bc1 = BatchCode("SCH-20251204-0001")
        bc2 = BatchCode("SCH-20251204-0002")
        assert bc1 != bc2

    def test_immutability(self):
        """BatchCode should be immutable (frozen dataclass)."""
        bc = BatchCode("SCH-20251204-0001")
        with pytest.raises((AttributeError, TypeError)):
            bc.value = "SCH-20251204-0002"  # type: ignore[misc]

    def test_hashable(self):
        """Frozen dataclass should be hashable (usable in sets/dicts)."""
        bc = BatchCode("SCH-20251204-0001")
        assert hash(bc) is not None
        s = {bc}
        assert bc in s

    def test_invalid_no_prefix(self):
        """Code without SCH prefix should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid batch code format"):
            BatchCode("ABC-20251204-0001")

    def test_invalid_wrong_date_length(self):
        """Code with wrong date segment length should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid batch code format"):
            BatchCode("SCH-202512-0001")

    def test_invalid_wrong_seq_length(self):
        """Code with wrong sequence segment length should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid batch code format"):
            BatchCode("SCH-20251204-001")

    def test_invalid_letters_in_date(self):
        """Code with letters in the date segment should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid batch code format"):
            BatchCode("SCH-YYYYMMDD-0001")

    def test_invalid_empty_string(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid batch code format"):
            BatchCode("")


class TestVolume:
    """Tests for Volume value object."""

    def test_valid_volume(self):
        """Valid volume should be accepted."""
        v = Volume(100.0)
        assert v.liters == 100.0

    def test_zero_volume(self):
        """Zero volume should be accepted."""
        v = Volume(0.0)
        assert v.liters == 0.0

    def test_fractional_volume(self):
        """Fractional volumes should be supported."""
        v = Volume(100.5)
        assert v.liters == pytest.approx(100.5)

    def test_negative_volume_raises(self):
        """Negative volume should raise ValueError."""
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            Volume(-1.0)

    def test_immutability(self):
        """Volume should be immutable."""
        v = Volume(100.0)
        with pytest.raises((AttributeError, TypeError)):
            v.liters = 200.0  # type: ignore[misc]

    def test_equality(self):
        """Two Volumes with same liters should be equal."""
        assert Volume(100.0) == Volume(100.0)

    def test_inequality(self):
        """Volumes with different liters should not be equal."""
        assert Volume(100.0) != Volume(200.0)

    def test_hashable(self):
        """Volume should be hashable."""
        v = Volume(100.0)
        assert {v} == {Volume(100.0)}

    def test_addition(self):
        """Adding two Volumes should return a new Volume."""
        result = Volume(100.0) + Volume(50.0)
        assert result.liters == pytest.approx(150.0)

    def test_addition_zero(self):
        """Adding zero Volume should return same value."""
        result = Volume(100.0) + Volume(0.0)
        assert result.liters == pytest.approx(100.0)

    def test_subtraction(self):
        """Subtracting Volume should return a new Volume."""
        result = Volume(100.0) - Volume(30.0)
        assert result.liters == pytest.approx(70.0)

    def test_subtraction_clamps_to_zero(self):
        """Subtracting more than available should clamp to zero."""
        result = Volume(50.0) - Volume(100.0)
        assert result.liters == 0.0

    def test_subtraction_exact(self):
        """Subtracting exactly the full amount should give zero."""
        result = Volume(100.0) - Volume(100.0)
        assert result.liters == 0.0

    def test_lt(self):
        """Less-than comparison should work."""
        assert Volume(50.0) < Volume(100.0)
        assert not Volume(100.0) < Volume(50.0)

    def test_le(self):
        """Less-than-or-equal comparison should work."""
        assert Volume(50.0) <= Volume(100.0)
        assert Volume(100.0) <= Volume(100.0)
        assert not Volume(100.0) <= Volume(50.0)

    def test_gt(self):
        """Greater-than comparison should work."""
        assert Volume(100.0) > Volume(50.0)
        assert not Volume(50.0) > Volume(100.0)

    def test_ge(self):
        """Greater-than-or-equal comparison should work."""
        assert Volume(100.0) >= Volume(50.0)
        assert Volume(100.0) >= Volume(100.0)
        assert not Volume(50.0) >= Volume(100.0)

    def test_str(self):
        """str(Volume) should include the unit."""
        assert str(Volume(100.0)) == "100.0L"
