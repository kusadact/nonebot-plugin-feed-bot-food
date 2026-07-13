from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .config import FeedBotFoodConfig
from .models import FoodCategory, quantize_weight


class ClassificationError(RuntimeError):
    """An LLM request failed before a classification could be obtained."""


@dataclass(frozen=True)
class Classification:
    category: FoodCategory
    value: Decimal | None = None
    too_much: bool = False


_TYPE_ALIASES = {
    "正餐": FoodCategory.MEAL,
    "主食": FoodCategory.MEAL,
    "meal": FoodCategory.MEAL,
    "水": FoodCategory.WATER,
    "water": FoodCategory.WATER,
    "甜品": FoodCategory.SNACK,
    "小食": FoodCategory.SNACK,
    "零食": FoodCategory.SNACK,
    "snack": FoodCategory.SNACK,
    "不可食用": FoodCategory.NON_EDIBLE,
    "non_edible": FoodCategory.NON_EDIBLE,
    "non-edible": FoodCategory.NON_EDIBLE,
    "unknown": FoodCategory.UNKNOWN,
    "无法确认": FoodCategory.UNKNOWN,
}


class FoodClassifier:
    def __init__(
        self,
        config: FeedBotFoodConfig,
        client: httpx.AsyncClient | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self.rng = rng or random.Random()

    async def classify(self, food: str) -> Classification:
        if not self.config.llm_ready:
            raise ClassificationError("LLM 未配置，请先配置 Base URL、API Key 和 Model")

        gain_ranges = self._effective_gain_ranges()
        payload = {
            "model": self.config.llm_model.strip(),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt(gain_ranges)},
                {"role": "user", "content": f"食物：{food.strip()}"},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.config.llm_api_key_value}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.llm_base_url.rstrip('/')}/chat/completions"

        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=payload, timeout=20.0)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, headers=headers, json=payload, timeout=20.0)
        except httpx.TimeoutException as exc:
            raise ClassificationError("LLM 请求超时") from exc
        except httpx.HTTPError as exc:
            raise ClassificationError(f"LLM 网络请求失败：{exc}") from exc

        if not response.is_success:
            detail = response.reason_phrase or "上游服务未成功处理请求"
            raise ClassificationError(f"LLM 请求失败（HTTP {response.status_code}）：{detail}")

        try:
            payload = response.json()
        except ValueError:
            return Classification(FoodCategory.UNKNOWN)
        return self._parse_response(payload, gain_ranges)

    def _system_prompt(
        self,
        gain_ranges: tuple[tuple[Decimal, Decimal], ...] | None = None,
    ) -> str:
        meal, water, snack = gain_ranges or self._effective_gain_ranges()
        return (
            "你是一个食物分类器。请根据用户给出的食物，把它归为 meal、water、snack、non_edible 或 unknown。"
            "meal 表示正餐或主食，water 表示水，snack 表示甜品/小食/零食，non_edible 表示不可食用。"
            "如果用户输入包含多个食物或饮品，必须把它们作为一个整体判断，只选择主要类别并返回一个 value；"
            "不要拆分食物，不要返回多个分类或多个 value。"
            "请识别输入中的数量、重量和单位（例如包、只、根、个、斤、kg），用于判断本次投喂是否超出可吃上限。"
            "如果用户请求的食物数量或重量超过对应类别的范围上限，必须设置 too_much 为 true，"
            "并将 value 截断为该类别的最大上限；这表示 Bot 吃不下更多，只吃最大限制的食物。"
            "如果没有超过上限，too_much 必须为 false。value 必须合理、符合食物分量，"
            "在范围内做小幅随机变化，不要机械地总是返回同一个值或直接取上限。"
            "如果无法确定，必须返回 unknown。请根据食物和本次有效范围给出 value（单位 kg）："
            f"meal {meal[0]}-{meal[1]}，water {water[0]}-{water[1]}，snack {snack[0]}-{snack[1]}。"
            '只能返回 JSON 对象，格式为 {"type":"meal|water|snack|non_edible|unknown","value":0.00,"too_much":true|false}，不要输出解释。'
        )

    def _parse_response(
        self,
        payload: Any,
        gain_ranges: tuple[tuple[Decimal, Decimal], ...] | None = None,
    ) -> Classification:
        content = self._extract_content(payload)
        if not content:
            return Classification(FoodCategory.UNKNOWN)
        content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content, flags=re.IGNORECASE)
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            return Classification(FoodCategory.UNKNOWN)
        if not isinstance(value, dict):
            return Classification(FoodCategory.UNKNOWN)

        category = _TYPE_ALIASES.get(str(value.get("type", "")).strip().lower(), FoodCategory.UNKNOWN)
        if category in (FoodCategory.UNKNOWN, FoodCategory.NON_EDIBLE):
            return Classification(category)
        try:
            gain = Decimal(str(value["value"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return Classification(FoodCategory.UNKNOWN)
        if not gain.is_finite():
            return Classification(FoodCategory.UNKNOWN)
        index = (FoodCategory.MEAL, FoodCategory.WATER, FoodCategory.SNACK).index(category)
        lower, upper = (gain_ranges or self._effective_gain_ranges())[index]
        too_much = value.get("too_much") is True or gain > upper
        gain = upper if too_much else min(max(gain, lower), upper)
        return Classification(category, gain, too_much)

    def _effective_gain_ranges(self) -> tuple[tuple[Decimal, Decimal], ...]:
        fluctuation = float(self.config.gain_range_fluctuation)
        ranges: list[tuple[Decimal, Decimal]] = []
        for base_lower, base_upper in self.config.category_gain_ranges:
            lower = quantize_weight(
                base_lower + Decimal(str(self.rng.uniform(-fluctuation, fluctuation)))
            )
            upper = quantize_weight(
                base_upper + Decimal(str(self.rng.uniform(-fluctuation, fluctuation)))
            )
            lower = max(Decimal("0.00"), lower)
            if upper <= lower:
                upper = quantize_weight(lower + Decimal("0.01"))
            ranges.append((lower, upper))
        return tuple(ranges)

    @staticmethod
    def _extract_content(payload: Any) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            ).strip()
        return ""
