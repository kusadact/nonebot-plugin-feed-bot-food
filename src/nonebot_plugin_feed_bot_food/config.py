from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

DEFAULT_RANDOM_GAIN_RANGE: tuple[Decimal, Decimal] = (
    Decimal("0.05"),
    Decimal("1.00"),
)


class FeedBotFoodConfig(BaseModel):
    """Configuration scoped under ``feed_bot_food__``."""

    initial_weight: Decimal = Decimal("48.00")
    metabolic_constant: Decimal = Decimal("5.00")
    metabolic_power: Decimal = Decimal("2.00")
    window_hours: int = 6
    category_limits: int = 3
    random_gain_range: tuple[Decimal, Decimal] = DEFAULT_RANDOM_GAIN_RANGE
    enable_groupmate_agent: bool = True

    @field_validator("initial_weight")
    @classmethod
    def validate_initial_weight(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("initial_weight must be greater than 0")
        return value

    @field_validator("metabolic_constant")
    @classmethod
    def validate_metabolic_constant(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("metabolic_constant must be greater than 0")
        return value

    @field_validator("metabolic_power")
    @classmethod
    def validate_metabolic_power(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("metabolic_power must be greater than 0")
        return value

    @field_validator("window_hours")
    @classmethod
    def validate_window_hours(cls, value: int) -> int:
        if value < 2 or value > 24 or 24 % value != 0:
            raise ValueError("window_hours must be a divisor of 24 between 2 and 24")
        return value

    @field_validator("category_limits")
    @classmethod
    def validate_category_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("category_limits must allow at least one feed")
        return value

    @field_validator("random_gain_range")
    @classmethod
    def validate_random_gain_range(
        cls,
        value: tuple[Decimal, Decimal],
    ) -> tuple[Decimal, Decimal]:
        if len(value) != 2:
            raise ValueError("random_gain_range must contain a lower and upper bound")
        lower, upper = value
        if not lower.is_finite() or not upper.is_finite() or lower < 0 or upper <= lower:
            raise ValueError("random_gain_range must satisfy 0 <= lower < upper")
        return value


class Config(BaseModel):
    feed_bot_food: FeedBotFoodConfig = Field(default_factory=FeedBotFoodConfig)
