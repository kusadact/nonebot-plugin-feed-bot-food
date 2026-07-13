from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

MONEY_QUANTUM = Decimal("0.01")


class FoodCategory(str, Enum):
    MEAL = "meal"
    WATER = "water"
    SNACK = "snack"
    NON_EDIBLE = "non_edible"
    UNKNOWN = "unknown"


EDIBLE_CATEGORIES = (FoodCategory.MEAL, FoodCategory.WATER, FoodCategory.SNACK)


def quantize_weight(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FeedEvent:
    user_id: str
    category: FoodCategory
    food: str
    gain: Decimal
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "category": self.category.value,
            "food": self.food,
            "gain": format(self.gain, ".2f"),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FeedEvent:
        return cls(
            user_id=str(value["user_id"]),
            category=FoodCategory(str(value["category"])),
            food=str(value.get("food", "")),
            gain=quantize_weight(Decimal(str(value["gain"]))),
            timestamp=datetime.fromisoformat(str(value["timestamp"])),
        )


@dataclass
class DailyStats:
    feed_count: int = 0
    gain: Decimal = Decimal("0.00")

    def to_dict(self) -> dict[str, Any]:
        return {"feed_count": self.feed_count, "gain": format(self.gain, ".2f")}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DailyStats:
        return cls(
            feed_count=int(value.get("feed_count", 0)),
            gain=quantize_weight(Decimal(str(value.get("gain", "0")))),
        )


@dataclass
class BotState:
    initial_weight: Decimal
    current_weight: Decimal
    total_feed_count: int = 0
    daily: dict[str, DailyStats] = field(default_factory=dict)
    events: list[FeedEvent] = field(default_factory=list)
    user_attempts: dict[str, dict[str, int]] = field(default_factory=dict)
    last_settled_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_weight": format(self.initial_weight, ".2f"),
            "current_weight": format(self.current_weight, ".2f"),
            "total_feed_count": self.total_feed_count,
            "daily": {key: value.to_dict() for key, value in self.daily.items()},
            "events": [event.to_dict() for event in self.events],
            "user_attempts": self.user_attempts,
            "last_settled_date": self.last_settled_date,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BotState:
        return cls(
            initial_weight=quantize_weight(Decimal(str(value["initial_weight"]))),
            current_weight=quantize_weight(Decimal(str(value["current_weight"]))),
            total_feed_count=int(value.get("total_feed_count", 0)),
            daily={
                str(key): DailyStats.from_dict(item)
                for key, item in dict(value.get("daily", {})).items()
            },
            events=[FeedEvent.from_dict(item) for item in value.get("events", [])],
            user_attempts={
                str(user_id): {str(window): int(count) for window, count in dict(windows).items()}
                for user_id, windows in dict(value.get("user_attempts", {})).items()
            },
            last_settled_date=(str(value["last_settled_date"]) if value.get("last_settled_date") else None),
        )


def empty_state(initial_weight: Decimal, settled_date: str) -> BotState:
    initial = quantize_weight(initial_weight)
    return BotState(
        initial_weight=initial,
        current_weight=initial,
        last_settled_date=settled_date,
    )
