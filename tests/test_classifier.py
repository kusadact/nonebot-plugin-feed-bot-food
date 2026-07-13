from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from nonebot_plugin_feed_bot_food.classifier import ClassificationError, FoodClassifier
from nonebot_plugin_feed_bot_food.config import FeedBotFoodConfig
from nonebot_plugin_feed_bot_food.models import FoodCategory


def make_config() -> FeedBotFoodConfig:
    return FeedBotFoodConfig(
        llm_base_url="https://example.com/v1",
        llm_api_key=SecretStr("secret"),
        llm_model="test-model",
    )


@pytest.mark.asyncio
async def test_classifier_parses_and_clamps_gain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"type":"meal","value":9}'}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await FoodClassifier(make_config(), client).classify("巨无霸")

    assert result.category == FoodCategory.MEAL
    assert result.value == Decimal("1.00")


@pytest.mark.asyncio
async def test_classifier_unknown_is_not_an_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        result = await FoodClassifier(make_config(), client).classify("神秘物品")
    assert result.category == FoodCategory.UNKNOWN
    assert result.value is None


def test_classifier_prompt_treats_multiple_foods_as_one_primary_category() -> None:
    prompt = FoodClassifier(make_config())._system_prompt()
    assert "多个食物或饮品" in prompt
    assert "只选择主要类别并返回一个 value" in prompt
    assert "不要拆分食物" in prompt


@pytest.mark.asyncio
async def test_classifier_reports_http_error_without_secret() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, text="Incorrect API key provided: secret-value")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ClassificationError, match=r"HTTP 401") as error:
            await FoodClassifier(make_config(), client).classify("面包")
    assert "secret-value" not in str(error.value)


@pytest.mark.asyncio
async def test_classifier_treats_redirect_as_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "/login"}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ClassificationError, match=r"HTTP 302"):
            await FoodClassifier(make_config(), client).classify("面包")
