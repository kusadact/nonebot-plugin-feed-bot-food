from __future__ import annotations

import random
from decimal import Decimal

from .config import FeedBotFoodConfig
from .models import quantize_weight


class RandomGainGenerator:
    """Generate one random weight gain for a successful feed."""

    def __init__(
        self,
        config: FeedBotFoodConfig,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.rng = rng or random.Random()

    def generate(self) -> Decimal:
        lower, upper = self.config.random_gain_range
        gain = quantize_weight(
            Decimal(str(self.rng.uniform(float(lower), float(upper))))
        )
        return min(max(gain, lower), upper)
