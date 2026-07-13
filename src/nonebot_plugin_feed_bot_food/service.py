from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .classifier import ClassificationError, FoodClassifier
from .config import FeedBotFoodConfig
from .limits import (
    attempt_count,
    category_available,
    hard_limit,
    localize,
    next_category_retry,
    now_local,
    prune_state,
    reserve_attempt,
    today_key,
    window_end,
    window_key,
)
from .models import BotState, DailyStats, FeedEvent, FoodCategory, empty_state, quantize_weight
from .storage import JsonStateStore


def _json_number(value: Decimal) -> float:
    return float(quantize_weight(value))


class FeedService:
    def __init__(
        self,
        config: FeedBotFoodConfig,
        store: JsonStateStore,
        classifier: FoodClassifier,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.classifier = classifier
        self.rng = rng or random.Random()

    async def feed(
        self,
        bot_id: str,
        user_id: str,
        food: str,
        moment: datetime | None = None,
    ) -> dict[str, Any]:
        food = food.strip()
        if not food:
            return {"status": "invalid_food", "message": "请提供要投喂的食物。"}
        moment = localize(moment or now_local())

        classifier_config = getattr(self.classifier, "config", None)
        if classifier_config is not None and not classifier_config.llm_ready:
            return {
                "status": "llm_error",
                "food": food,
                "message": "LLM 未配置，请先配置 Base URL、API Key 和 Model",
            }

        reservation = await self._reserve_llm_attempt(bot_id, user_id, moment)
        if reservation is not None:
            return reservation

        try:
            classification = await self.classifier.classify(food)
        except ClassificationError as exc:
            return {"status": "llm_error", "message": str(exc), "food": food}

        if classification.category == FoodCategory.UNKNOWN or classification.value is None:
            return {"status": "ignored", "food": food, "silent": True}
        if classification.category == FoodCategory.NON_EDIBLE:
            return {
                "status": "non_edible",
                "food": food,
                "message": "这个东西不可食用。",
            }

        async with self.store.lock:
            root = await self.store.load()
            state, created = self._get_state(root, bot_id, moment)
            settled = self._settle_state(state, moment)
            category = classification.category
            if not category_available(state, user_id, category, moment, self.config):
                retry_at = next_category_retry(state, user_id, category, moment, self.config)
                if created or settled:
                    self._sync_state(root, bot_id, state)
                    await self.store.save(root)
                return {
                    "status": "category_limited",
                    "food": food,
                    "category": category.value,
                    "retry_at": retry_at.isoformat(),
                    "message": f"这一类食物投喂次数已用完，请在 {retry_at.strftime('%H:%M')} 后再投喂。",
                }

            gain = quantize_weight(classification.value)
            event = FeedEvent(
                user_id=user_id,
                category=category,
                food=food,
                gain=gain,
                timestamp=moment,
            )
            state.events.append(event)
            state.total_feed_count += 1
            daily = state.daily.setdefault(today_key(moment), DailyStats())
            daily.feed_count += 1
            daily.gain = quantize_weight(daily.gain + gain)
            state.current_weight = quantize_weight(state.current_weight + gain)
            prune_state(state, moment, self.config.window_hours)
            self._sync_state(root, bot_id, state)
            await self.store.save(root)
            return {
                "status": "success",
                "food": food,
                "category": category.value,
                "gain_kg": _json_number(gain),
                "current_weight_kg": _json_number(state.current_weight),
            }

    async def get_status(self, bot_id: str, moment: datetime | None = None) -> dict[str, Any]:
        moment = localize(moment or now_local())
        async with self.store.lock:
            root = await self.store.load()
            state, created = self._get_state(root, bot_id, moment)
            changed = self._settle_state(state, moment)
            daily = state.daily.get(today_key(moment), DailyStats())
            if changed or created:
                self._sync_state(root, bot_id, state)
                await self.store.save(root)
            return {
                "status": "success",
                "current_weight_kg": _json_number(state.current_weight),
                "today_feed_count": daily.feed_count,
                "today_gain_kg": _json_number(daily.gain),
                "total_feed_count": state.total_feed_count,
            }

    async def settle(self, bot_id: str, moment: datetime | None = None) -> None:
        moment = localize(moment or now_local())
        async with self.store.lock:
            root = await self.store.load()
            state, created = self._get_state(root, bot_id, moment)
            changed = self._settle_state(state, moment)
            if changed or created:
                self._sync_state(root, bot_id, state)
                await self.store.save(root)

    async def _reserve_llm_attempt(
        self,
        bot_id: str,
        user_id: str,
        moment: datetime,
    ) -> dict[str, Any] | None:
        async with self.store.lock:
            root = await self.store.load()
            state, _ = self._get_state(root, bot_id, moment)
            self._settle_state(state, moment)
            current_window = window_key(moment, self.config.window_hours)
            limit = hard_limit(self.config)
            if attempt_count(state, user_id, current_window) >= limit:
                retry_at = window_end(moment, self.config.window_hours)
                return {
                    "status": "request_limited",
                    "retry_at": retry_at.isoformat(),
                    "message": f"你投喂的太多了，请在 {retry_at.strftime('%H:%M')} 后再投喂。",
                }
            reserve_attempt(state, user_id, current_window)
            prune_state(state, moment, self.config.window_hours)
            self._sync_state(root, bot_id, state)
            await self.store.save(root)
        return None

    def _get_state(self, root: dict[str, Any], bot_id: str, moment: datetime) -> tuple[BotState, bool]:
        bots = root.setdefault("bots", {})
        raw_state = bots.get(str(bot_id))
        if raw_state is None:
            current_day = date.fromisoformat(today_key(moment))
            state = empty_state(self.config.initial_weight, (current_day - timedelta(days=1)).isoformat())
            bots[str(bot_id)] = state.to_dict()
            return state, True
        state = BotState.from_dict(raw_state)
        return state, False

    @staticmethod
    def _sync_state(root: dict[str, Any], bot_id: str, state: BotState) -> None:
        root.setdefault("bots", {})[str(bot_id)] = state.to_dict()

    def _settle_state(self, state: BotState, moment: datetime) -> bool:
        current_day = date.fromisoformat(today_key(moment))
        yesterday = current_day - timedelta(days=1)
        if state.last_settled_date is None:
            state.last_settled_date = yesterday.isoformat()
            return True
        last_settled = date.fromisoformat(state.last_settled_date)
        changed = False
        while last_settled < yesterday:
            target = last_settled + timedelta(days=1)
            daily = state.daily.get(target.isoformat(), DailyStats())
            if daily.gain > 0 and state.current_weight > 0:
                lower = Decimal("0.95") - self.config.decay_fluctuation
                upper = Decimal("0.95") + self.config.decay_fluctuation
                coefficient = Decimal(str(self.rng.uniform(float(lower), float(upper))))
                loss = quantize_weight(
                    daily.gain * coefficient * (state.initial_weight / state.current_weight)
                )
                state.current_weight = max(
                    Decimal("35.00"),
                    quantize_weight(state.current_weight - loss),
                )
            last_settled = target
            state.last_settled_date = target.isoformat()
            changed = True
        return changed
