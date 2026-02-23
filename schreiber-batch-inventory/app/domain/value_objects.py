"""Domain value objects for type-safe business concepts."""

from __future__ import annotations

import re
from dataclasses import dataclass


_BATCH_CODE_PATTERN: re.Pattern[str] = re.compile(r"^SCH-\d{8}-\d{4}$")


@dataclass(frozen=True)
class BatchCode:
    """
    Immutable value object for a batch code.

    Enforces the pattern SCH-YYYYMMDD-XXXX at construction time.
    """

    value: str

    def __post_init__(self) -> None:
        if not _BATCH_CODE_PATTERN.match(self.value):
            raise ValueError(
                f"Invalid batch code format: '{self.value}'. "
                "Expected format: SCH-YYYYMMDD-XXXX",
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Volume:
    """
    Immutable value object for a volume in liters.

    Enforces non-negative values and provides arithmetic operators.
    """

    liters: float

    def __post_init__(self) -> None:
        if self.liters < 0.0:
            raise ValueError(f"Volume cannot be negative: {self.liters}")

    def __add__(self, other: Volume) -> Volume:
        return Volume(self.liters + other.liters)

    def __sub__(self, other: Volume) -> Volume:
        """Subtract volumes; result is clamped to zero (no negative volumes)."""
        return Volume(max(0.0, self.liters - other.liters))

    def __lt__(self, other: Volume) -> bool:
        return self.liters < other.liters

    def __le__(self, other: Volume) -> bool:
        return self.liters <= other.liters

    def __gt__(self, other: Volume) -> bool:
        return self.liters > other.liters

    def __ge__(self, other: Volume) -> bool:
        return self.liters >= other.liters

    def __str__(self) -> str:
        return f"{self.liters}L"
