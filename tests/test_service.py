from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from nonebot_plugin_feed_bot_food.config import FeedBotFoodConfig
from nonebot_plugin_feed_bot_food.service import FeedService
from nonebot_plugin_feed_bot_food.storage import JsonStateStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def moment(hour: int, minute: int = 0, day: int = 13) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=SHANGHAI)


class FixedGainGenerator:
    def __init__(self, value: str = "0.62") -> None:
        self.value = Decimal(value)
        self.calls = 0

    def generate(self) -> Decimal:
        self.calls += 1
        return self.value


class BrokenGainGenerator:
    def generate(self) -> Decimal:
        raise RuntimeError("gain generator crashed")


def service_for(gain_generator: object, path: Path, **kwargs: object) -> FeedService:
    return FeedService(
        FeedBotFoodConfig(**kwargs),
        JsonStateStore(path),
        gain_generator,  # type: ignore[arg-type]
    )


def test_metabolic_power_defaults_to_two() -> None:
    assert FeedBotFoodConfig().metabolic_power == Decimal("2.00")


@pytest.mark.asyncio
async def test_total_limit_is_the_only_feed_limit() -> None:
    with TemporaryDirectory() as directory:
        generator = FixedGainGenerator()
        service = service_for(generator, Path(directory) / "state.json")
        assert (await service.feed("bot", "user", "饭", moment(8)))['status'] == "success"
        assert (await service.feed("bot", "user", "水", moment(8)))['status'] == "success"
        assert (await service.feed("bot", "user", "石头", moment(8)))['status'] == "success"
        result = await service.feed("bot", "user", "蛋糕", moment(8))

    assert result["status"] == "total_limited"
    assert generator.calls == 3


@pytest.mark.asyncio
async def test_window_boundary_has_no_protection_delay() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        generator = FixedGainGenerator("0.30")
        service = service_for(generator, path)
        assert (await service.feed("bot", "user", "食物", moment(11, 30)))['status'] == "success"
        assert (await service.feed("bot", "user", "食物", moment(11, 50)))['status'] == "success"
        assert (await service.feed("bot", "user", "食物", moment(12, 5)))['status'] == "success"
        assert (await service.feed("bot", "user", "食物", moment(12, 5)))['status'] == "success"
        assert (await service.feed("bot", "user", "食物", moment(12, 5)))['status'] == "success"


@pytest.mark.asyncio
async def test_status_contains_today_yesterday_and_total_fields() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(FixedGainGenerator(), Path(directory) / "state.json")
        await service.feed("bot", "user", "饭", moment(8))
        result = await service.get_status("bot", moment(8))

    assert result == {
        "status": "success",
        "current_weight_kg": 48.00,
        "today_feed_count": 1,
        "today_gain_kg": 0.62,
        "yesterday_feed_count": 0,
        "yesterday_gain_kg": 0.0,
        "yesterday_weight_change_kg": 0.0,
        "total_feed_count": 1,
        "total_gain_kg": 0.62,
    }


@pytest.mark.asyncio
async def test_feed_result_reports_weight_without_today_gain() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(FixedGainGenerator("0.62"), Path(directory) / "state.json")
        result = await service.feed("bot", "user", "饭", moment(8))

    assert result["current_weight_kg"] == 48.00
    assert result["gain_kg"] == 0.62
    assert "category" not in result


@pytest.mark.asyncio
async def test_status_reports_historical_cumulative_gain() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(FixedGainGenerator("0.62"), Path(directory) / "state.json")
        await service.feed("bot", "user", "饭", moment(8, day=12))
        await service.feed("bot", "user", "饭", moment(8, day=13))
        result = await service.get_status("bot", moment(8, day=13))

    assert result["total_gain_kg"] == 1.24


@pytest.mark.asyncio
async def test_daily_metabolism_uses_yesterday_intake_and_keeps_two_decimals() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(
            FixedGainGenerator("0.50"),
            Path(directory) / "state.json",
        )
        await service.feed("bot", "user", "饭", moment(12, day=12))
        result = await service.get_status("bot", moment(6, day=13))

    assert result["current_weight_kg"] == 46.47
    assert result["today_feed_count"] == 0
    assert result["today_gain_kg"] == 0.0
    assert result["yesterday_feed_count"] == 1
    assert result["yesterday_gain_kg"] == 0.5
    assert result["yesterday_weight_change_kg"] == -1.53
    assert result["total_feed_count"] == 1


@pytest.mark.asyncio
async def test_standard_weight_is_stable_when_intake_matches_metabolism() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(
            FixedGainGenerator("5.00"),
            Path(directory) / "state.json",
        )
        await service.feed("bot", "user", "饭", moment(12, day=12))
        result = await service.get_status("bot", moment(6, day=13))

    assert result["current_weight_kg"] == 48.00
    assert result["yesterday_weight_change_kg"] == 0.00


@pytest.mark.asyncio
async def test_large_intake_uses_nonlinear_weight_change() -> None:
    with TemporaryDirectory() as directory:
        service = service_for(
            FixedGainGenerator("15.00"),
            Path(directory) / "state.json",
        )
        await service.feed("bot", "user", "饭", moment(12, day=12))
        result = await service.get_status("bot", moment(6, day=13))

    assert result["current_weight_kg"] == 51.00
    assert result["yesterday_weight_change_kg"] == 3.00


@pytest.mark.asyncio
async def test_legacy_state_is_migrated_and_written_as_schema_v3() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "bots": {
                        "bot": {
                            "initial_weight": "48.00",
                            "current_weight": "48.50",
                            "total_feed_count": 1,
                            "daily": {"2026-07-12": {"feed_count": 1, "gain": "0.50"}},
                            "events": [
                                {
                                    "user_id": "user",
                                    "category": "meal",
                                    "food": "饭",
                                    "gain": "0.50",
                                    "timestamp": "2026-07-12T08:00:00+08:00",
                                }
                            ],
                            "user_attempts": {},
                            "last_settled_date": "2026-07-12",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        data = await JsonStateStore(path).load()
        written = json.loads(path.read_text(encoding="utf-8"))

    assert data["schema_version"] == 3
    assert data["bots"]["bot"]["daily"]["2026-07-12"]["weight_change"] == "0.00"
    assert "category" not in data["bots"]["bot"]["events"][0]
    assert "user_attempts" not in data["bots"]["bot"]
    assert written == data


@pytest.mark.asyncio
async def test_schema_v2_state_is_migrated_to_schema_v3() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "bots": {
                        "bot": {
                            "initial_weight": "48.00",
                            "current_weight": "48.50",
                            "total_feed_count": 1,
                            "daily": {},
                            "events": [
                                {
                                    "user_id": "user",
                                    "category": "meal",
                                    "food": "饭",
                                    "gain": "0.50",
                                    "timestamp": "2026-07-12T08:00:00+08:00",
                                }
                            ],
                            "user_attempts": {"user": {"2026-07-12T06:00:00+08:00": 1}},
                            "last_settled_date": "2026-07-12",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        data = await JsonStateStore(path).load()

    assert data["schema_version"] == 3
    assert "category" not in data["bots"]["bot"]["events"][0]
    assert "user_attempts" not in data["bots"]["bot"]


@pytest.mark.asyncio
async def test_non_empty_feed_does_not_require_llm() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        config = FeedBotFoodConfig()
        service = FeedService(
            config,
            JsonStateStore(path),
            FixedGainGenerator(),  # type: ignore[arg-type]
        )
        result = await service.feed("bot", "user", "石头", moment(8))

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_unexpected_feed_failure_returns_a_replyable_result() -> None:
    with TemporaryDirectory() as directory:
        service = FeedService(
            FeedBotFoodConfig(),
            JsonStateStore(Path(directory) / "state.json"),
            BrokenGainGenerator(),  # type: ignore[arg-type]
        )
        result = await service.feed("bot", "user", "饭", moment(8))

    assert result == {
        "status": "internal_error",
        "food": "饭",
        "message": "投喂暂时失败，请稍后再试。",
        "reply_required": True,
    }


@pytest.mark.asyncio
async def test_empty_feed_does_not_change_state() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        service = service_for(FixedGainGenerator(), path)
        result = await service.feed("bot", "user", "  ", moment(8))
        data = await JsonStateStore(path).load()

    assert result == {
        "status": "invalid_food",
        "message": "请提供要投喂的食物。",
        "reply_required": True,
    }
    assert data["bots"] == {}


@pytest.mark.asyncio
async def test_old_category_state_can_be_read() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        service = service_for(FixedGainGenerator(), path)
        root = await JsonStateStore(path).load()
        root["bots"]["bot"] = {
            "initial_weight": "48.00",
            "current_weight": "48.50",
            "total_feed_count": 1,
            "daily": {"2026-07-12": {"feed_count": 1, "gain": "0.50", "weight_change": "0.00"}},
            "events": [
                {
                    "user_id": "user",
                    "category": "meal",
                    "food": "饭",
                    "gain": "0.50",
                    "timestamp": "2026-07-12T08:00:00+08:00",
                }
            ],
            "user_attempts": {},
            "last_settled_date": "2026-07-12",
        }
        await JsonStateStore(path).save(root)

        result = await service.get_status("bot", moment(8, day=13))

    assert result["total_feed_count"] == 1
