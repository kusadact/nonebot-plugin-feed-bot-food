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
    def __init__(
        self,
        category: FoodCategory = FoodCategory.MEAL,
        value: str = "0.62",
        too_much: bool = False,
    ) -> None:
        self.category = category
        self.value = Decimal(value)
        self.too_much = too_much
        self.calls = 0

    async def classify(self, food: str) -> Classification:
        self.calls += 1
        return Classification(self.category, self.value, self.too_much)


class BrokenClassifier:
    async def classify(self, food: str) -> Classification:
        raise RuntimeError("classifier crashed")


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
async def test_total_limit_and_hard_llm_limit() -> None:
    with TemporaryDirectory() as directory:
        classifier = FixedClassifier()
        service = service_for(classifier, Path(directory) / "state.json")
        assert (await service.feed("bot", "user", "饭", moment(8)))['status'] == "success"
        classifier.category = FoodCategory.WATER
        assert (await service.feed("bot", "user", "水", moment(8)))['status'] == "success"
        classifier.category = FoodCategory.SNACK
        assert (await service.feed("bot", "user", "蛋糕", moment(8)))['status'] == "success"
        for _ in range(2):
            assert (await service.feed("bot", "user", "饭", moment(8)))['status'] == "total_limited"
        result = await service.feed("bot", "user", "饭", moment(8))

    assert result["status"] == "request_limited"
    assert classifier.calls == 5


@pytest.mark.asyncio
async def test_window_boundary_has_no_protection_delay() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        classifier = FixedClassifier(FoodCategory.MEAL, "0.30")
        service = service_for(classifier, path)
        assert (await service.feed("bot", "user", "正餐", moment(11, 30)))['status'] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(11, 50)))['status'] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(12, 5)))['status'] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(12, 5)))['status'] == "success"
        assert (await service.feed("bot", "user", "正餐", moment(12, 5)))['status'] == "success"


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
    assert result["reply_required"] is True
    assert result["message"] == "投喂功能暂时不可用，请先配置食物分类服务。"
    assert data["bots"] == {}


@pytest.mark.asyncio
async def test_unexpected_feed_failure_returns_a_replyable_result() -> None:
    with TemporaryDirectory() as directory:
        service = FeedService(
            FeedBotFoodConfig(),
            JsonStateStore(Path(directory) / "state.json"),
            BrokenClassifier(),
        )
        result = await service.feed("bot", "user", "饭", moment(8))

    assert result == {
        "status": "internal_error",
        "food": "饭",
        "message": "投喂暂时失败，请稍后再试。",
        "reply_required": True,
    }


@pytest.mark.asyncio
async def test_non_edible_returns_message_without_changing_state() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        classifier = FixedClassifier(FoodCategory.NON_EDIBLE)
        service = service_for(classifier, path)
        result = await service.feed("bot", "user", "猫薄荷", moment(8))
        data = await JsonStateStore(path).load()

    assert result == {
        "status": "non_edible",
        "food": "猫薄荷",
        "message": "猫薄荷不可食用。",
        "reply_required": True,
    }
    state = data["bots"]["bot"]
    assert state["current_weight"] == "48.00"
    assert state["total_feed_count"] == 0
    assert state["events"] == []


@pytest.mark.asyncio
async def test_unknown_classification_returns_message_without_recording_feed() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        classifier = FixedClassifier(FoodCategory.UNKNOWN)
        service = service_for(classifier, path)
        result = await service.feed("bot", "user", "未知物品", moment(8))
        data = await JsonStateStore(path).load()

    assert result == {
        "status": "ignored",
        "food": "未知物品",
        "message": "无法确认这个食物的分类，未进行投喂。",
        "reply_required": True,
    }
    state = data["bots"]["bot"]
    assert state["current_weight"] == "48.00"
    assert state["total_feed_count"] == 0
    assert state["events"] == []


@pytest.mark.asyncio
async def test_over_limit_feed_is_capped_without_fixed_message() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(
            FixedClassifier(value="0.62", too_much=True),
            Path(directory) / "state.json",
        )
        result = await service.feed("bot", "user", "16包方便面", moment(8))

    assert result["status"] == "success"
    assert result["too_much"] is True
    assert result["gain_kg"] == 0.62
    assert "message" not in result
