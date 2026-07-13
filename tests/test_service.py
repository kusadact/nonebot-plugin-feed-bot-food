from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from nonebot_plugin_feed_bot_food.classifier import Classification, FoodClassifier
from nonebot_plugin_feed_bot_food.config import FeedBotFoodConfig
from nonebot_plugin_feed_bot_food.models import FoodCategory
from nonebot_plugin_feed_bot_food.service import FeedService
from nonebot_plugin_feed_bot_food.storage import JsonStateStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def moment(hour: int, minute: int = 0, day: int = 13) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=SHANGHAI)


class FixedClassifier:
    def __init__(self, category: FoodCategory = FoodCategory.MEAL, value: str = "0.62") -> None:
        self.category = category
        self.value = Decimal(value)
        self.calls = 0

    async def classify(self, food: str) -> Classification:
        self.calls += 1
        return Classification(self.category, self.value)


class FixedRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def uniform(self, lower: float, upper: float) -> float:
        assert lower <= self.value <= upper
        return self.value


def service_for(classifier: FixedClassifier, path: Path, **kwargs: object) -> FeedService:
    return FeedService(
        FeedBotFoodConfig(**kwargs),
        JsonStateStore(path),
        classifier,
        rng=FixedRng(0.95),
    )


@pytest.mark.asyncio
async def test_category_limit_and_hard_llm_limit() -> None:
    with TemporaryDirectory() as directory:
        classifier = FixedClassifier()
        service = service_for(classifier, Path(directory) / "state.json")
        assert (await service.feed("bot", "user", "饭", moment(8)))['status'] == "success"
        for _ in range(4):
            assert (await service.feed("bot", "user", "饭", moment(8)))['status'] == "category_limited"
        result = await service.feed("bot", "user", "饭", moment(8))

    assert result["status"] == "request_limited"
    assert classifier.calls == 5


@pytest.mark.asyncio
async def test_boundary_slot_is_delayed_per_category() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        meal_classifier = FixedClassifier(FoodCategory.MEAL)
        service = service_for(meal_classifier, path)
        assert (await service.feed("bot", "user", "正餐", moment(11, 38)))['status'] == "success"
        delayed = await service.feed("bot", "user", "正餐", moment(12, 5))
        assert delayed["status"] == "category_limited"
        assert delayed["retry_at"].startswith("2026-07-13T13:38")

        water_classifier = FixedClassifier(FoodCategory.WATER, "0.10")
        service.classifier = water_classifier
        assert (await service.feed("bot", "user", "水", moment(12, 5)))['status'] == "success"

        service.classifier = meal_classifier
        assert (await service.feed("bot", "user", "正餐", moment(13, 38)))['status'] == "success"


@pytest.mark.asyncio
async def test_multiple_boundary_slots_recover_independently_without_new_delay() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        classifier = FixedClassifier(FoodCategory.MEAL, "0.30")
        service = service_for(classifier, path, category_limits=(2, 1, 1))

        assert (await service.feed("bot", "user", "正餐", moment(11, 30)))['status'] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(11, 50)))['status'] == "success"

        first_recovered = await service.feed("bot", "user", "正餐", moment(13, 30))
        assert first_recovered["status"] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(13, 40)))["status"] == "category_limited"
        assert (await service.feed("bot", "user", "正餐", moment(13, 50)))['status'] == "success"

        # 13:30/13:50 的新投喂不在 17:00-18:00 边界保护区，18:00 不应再次顺延。
        assert (await service.feed("bot", "user", "正餐", moment(18, 0)))['status'] == "success"


@pytest.mark.asyncio
async def test_retry_uses_first_next_window_slot_release() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(
            FixedClassifier(FoodCategory.MEAL, "0.30"),
            Path(directory) / "state.json",
            category_limits=(2, 1, 1),
        )
        assert (await service.feed("bot", "user", "正餐", moment(16, 30)))['status'] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(17, 30)))['status'] == "success"

        limited = await service.feed("bot", "user", "正餐", moment(17, 40))
        assert limited["status"] == "category_limited"
        assert limited["retry_at"].startswith("2026-07-13T18:00")
        assert (await service.feed("bot", "user", "正餐", moment(18, 0)))['status'] == "success"


@pytest.mark.asyncio
async def test_status_only_contains_four_public_fields() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(FixedClassifier(), Path(directory) / "state.json")
        await service.feed("bot", "user", "饭", moment(8))
        result = await service.get_status("bot", moment(8))

    assert result == {
        "status": "success",
        "current_weight_kg": 48.62,
        "today_feed_count": 1,
        "today_gain_kg": 0.62,
        "total_feed_count": 1,
    }


@pytest.mark.asyncio
async def test_daily_decay_uses_yesterday_gain_and_keeps_two_decimals() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(
            FixedClassifier(value="0.50"),
            Path(directory) / "state.json",
        )
        await service.feed("bot", "user", "饭", moment(12, day=12))
        result = await service.get_status("bot", moment(6, day=13))

    assert result["current_weight_kg"] == 48.03
    assert result["today_feed_count"] == 0
    assert result["today_gain_kg"] == 0.0
    assert result["total_feed_count"] == 1


@pytest.mark.asyncio
async def test_missing_llm_config_does_not_change_state() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        config = FeedBotFoodConfig()
        service = FeedService(config, JsonStateStore(path), FoodClassifier(config))
        result = await service.feed("bot", "user", "饭", moment(8))
        data = await JsonStateStore(path).load()

    assert result["status"] == "llm_error"
    assert data["bots"] == {}
