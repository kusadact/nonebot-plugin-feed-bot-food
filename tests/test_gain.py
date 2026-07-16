from __future__ import annotations

from decimal import Decimal

import pytest

from nonebot_plugin_feed_bot_food.config import FeedBotFoodConfig
from nonebot_plugin_feed_bot_food.gain import RandomGainGenerator


def test_random_gain_range_defaults_to_point_zero_five_to_one() -> None:
    assert FeedBotFoodConfig().random_gain_range == (
        Decimal("0.05"),
        Decimal("1.00"),
    )


def test_random_gain_range_can_be_configured() -> None:
    config = FeedBotFoodConfig(random_gain_range=(Decimal("0.20"), Decimal("0.80")))

    assert config.random_gain_range == (Decimal("0.20"), Decimal("0.80"))


@pytest.mark.parametrize(
    "value",
    [
        (Decimal("0.50"), Decimal("0.50")),
        (Decimal("-0.10"), Decimal("0.50")),
        (Decimal("0.10"), Decimal("Infinity")),
    ],
)
def test_random_gain_range_must_be_a_finite_ascending_range(
    value: tuple[Decimal, Decimal],
) -> None:
    with pytest.raises(ValueError, match="random_gain_range"):
        FeedBotFoodConfig(random_gain_range=value)


def test_random_gain_is_quantized_and_clamped_to_configured_range() -> None:
    class FixedRng:
        def uniform(self, lower: float, upper: float) -> float:
            assert lower == 0.20
            assert upper == 0.80
            return 0.456

    config = FeedBotFoodConfig(random_gain_range=(Decimal("0.20"), Decimal("0.80")))

    assert RandomGainGenerator(config, rng=FixedRng()).generate() == Decimal("0.46")
