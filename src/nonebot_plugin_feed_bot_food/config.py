from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, SecretStr, field_validator

DEFAULT_GAIN_RANGES: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("0.30"), Decimal("1.00")),
    (Decimal("0.05"), Decimal("0.30")),
    (Decimal("0.10"), Decimal("0.50")),
)


class FeedBotFoodConfig(BaseModel):
    """Configuration scoped under ``feed_bot_food__``."""

    initial_weight: Decimal = Decimal("48.00")
    window_hours: int = 6
    category_limits: int = 3
    category_gain_ranges: tuple[tuple[Decimal, Decimal], ...] = DEFAULT_GAIN_RANGES
    gain_range_fluctuation: Decimal = Decimal("0.15")
    decay_fluctuation: Decimal = Decimal("0.10")
    enable_groupmate_agent: bool = True
    llm_base_url: str = ""
    llm_api_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    llm_model: str = ""

    @field_validator("initial_weight")
    @classmethod
    def validate_initial_weight(cls, value: Decimal) -> Decimal:
        if value <= Decimal("35.00"):
            raise ValueError("initial_weight must be greater than 35.00")
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

    @field_validator("category_gain_ranges")
    @classmethod
    def validate_gain_ranges(
        cls,
        value: tuple[tuple[Decimal, Decimal], ...],
    ) -> tuple[tuple[Decimal, Decimal], ...]:
        if len(value) != 3:
            raise ValueError("category_gain_ranges must contain meal, water and snack ranges")
        for lower, upper in value:
            if lower < 0 or upper <= lower:
                raise ValueError("each gain range must satisfy 0 <= lower < upper")
        return value

    @field_validator("gain_range_fluctuation")
    @classmethod
    def validate_gain_range_fluctuation(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("gain_range_fluctuation cannot be negative")
        return value

    @field_validator("decay_fluctuation")
    @classmethod
    def validate_decay_fluctuation(cls, value: Decimal) -> Decimal:
        if value < 0 or value >= Decimal("0.95"):
            raise ValueError("decay_fluctuation must be between 0 and 0.95")
        return value

    @property
    def llm_api_key_value(self) -> str:
        return self.llm_api_key.get_secret_value().strip()

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_base_url.strip() and self.llm_api_key_value and self.llm_model.strip())


class Config(BaseModel):
    feed_bot_food: FeedBotFoodConfig = Field(default_factory=FeedBotFoodConfig)
