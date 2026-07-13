from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import FeedBotFoodConfig
from .models import BotState, FeedEvent, FoodCategory

BOUNDARY_GUARD = timedelta(hours=1)
SLOT_DELAY = timedelta(hours=2)
SIX_AM = time(hour=6)
APP_TIMEZONE = ZoneInfo("Asia/Shanghai")


def localize(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=APP_TIMEZONE)
    return moment.astimezone(APP_TIMEZONE)


def now_local() -> datetime:
    return datetime.now(APP_TIMEZONE)


def today_key(moment: datetime) -> str:
    moment = localize(moment)
    day = moment.date() if moment.time() >= SIX_AM else moment.date() - timedelta(days=1)
    return day.isoformat()


def window_start(moment: datetime, window_hours: int) -> datetime:
    moment = localize(moment)
    day = moment.date() if moment.time() >= SIX_AM else moment.date() - timedelta(days=1)
    anchor = datetime.combine(day, SIX_AM, tzinfo=moment.tzinfo)
    elapsed = moment - anchor
    index = elapsed // timedelta(hours=window_hours)
    return anchor + index * timedelta(hours=window_hours)


def window_end(moment: datetime, window_hours: int) -> datetime:
    return window_start(moment, window_hours) + timedelta(hours=window_hours)


def window_key(moment: datetime, window_hours: int) -> str:
    return window_start(moment, window_hours).isoformat()


def hard_limit(config: FeedBotFoodConfig) -> int:
    return math.ceil(sum(config.category_limits) * 1.5)


def attempt_count(state: BotState, user_id: str, current_window_key: str) -> int:
    return state.user_attempts.get(user_id, {}).get(current_window_key, 0)


def reserve_attempt(state: BotState, user_id: str, current_window_key: str) -> None:
    user_attempts = state.user_attempts.setdefault(user_id, {})
    user_attempts[current_window_key] = user_attempts.get(current_window_key, 0) + 1


def category_limit(config: FeedBotFoodConfig, category: FoodCategory) -> int:
    return config.category_limits[(FoodCategory.MEAL, FoodCategory.WATER, FoodCategory.SNACK).index(category)]


def _is_in_window(event: FeedEvent, start: datetime, end: datetime) -> bool:
    event_time = localize(event.timestamp)
    return start <= event_time < end


def _carryover_events(
    state: BotState,
    user_id: str,
    category: FoodCategory,
    start: datetime,
    now: datetime,
) -> list[FeedEvent]:
    guard_start = start - BOUNDARY_GUARD
    return [
        event
        for event in state.events
        if event.user_id == user_id
        and event.category == category
        and guard_start <= localize(event.timestamp) < start
        and localize(event.timestamp) + SLOT_DELAY > now
    ]


def category_usage(
    state: BotState,
    user_id: str,
    category: FoodCategory,
    moment: datetime,
    config: FeedBotFoodConfig,
) -> tuple[int, int]:
    moment = localize(moment)
    start = window_start(moment, config.window_hours)
    end = start + timedelta(hours=config.window_hours)
    current = sum(
        1
        for event in state.events
        if event.user_id == user_id and event.category == category and _is_in_window(event, start, end)
    )
    carryover = len(_carryover_events(state, user_id, category, start, moment))
    return current, carryover


def category_available(
    state: BotState,
    user_id: str,
    category: FoodCategory,
    moment: datetime,
    config: FeedBotFoodConfig,
) -> bool:
    current, carryover = category_usage(state, user_id, category, moment, config)
    return current + carryover < category_limit(config, category)


def next_category_retry(
    state: BotState,
    user_id: str,
    category: FoodCategory,
    moment: datetime,
    config: FeedBotFoodConfig,
) -> datetime:
    moment = localize(moment)
    start = window_start(moment, config.window_hours)
    current_count, carryover_count = category_usage(state, user_id, category, moment, config)
    limit = category_limit(config, category)
    if current_count < limit and carryover_count:
        active_carryovers = _carryover_events(state, user_id, category, start, moment)
        if active_carryovers:
            return min(localize(event.timestamp) + SLOT_DELAY for event in active_carryovers)
    next_start = start + timedelta(hours=config.window_hours)
    guard_start = next_start - BOUNDARY_GUARD
    next_window_carryovers = []
    for event in state.events:
        event_time = localize(event.timestamp)
        if (
            event.user_id == user_id
            and event.category == category
            and guard_start <= event_time < next_start
        ):
            next_window_carryovers.append(event_time + SLOT_DELAY)
    if len(next_window_carryovers) >= limit and next_window_carryovers:
        return min(next_window_carryovers)
    return next_start


def prune_state(state: BotState, moment: datetime, window_hours: int) -> None:
    moment = localize(moment)
    event_cutoff = moment - timedelta(days=3)
    state.events = [event for event in state.events if localize(event.timestamp) >= event_cutoff]
    active_windows = {
        window_key(moment - timedelta(days=2), window_hours),
        window_key(moment - timedelta(days=1), window_hours),
        window_key(moment, window_hours),
    }
    for user_id, attempts in list(state.user_attempts.items()):
        state.user_attempts[user_id] = {
            key: count for key, count in attempts.items() if key in active_windows
        }
        if not state.user_attempts[user_id]:
            del state.user_attempts[user_id]


def date_from_key(value: str) -> date:
    return date.fromisoformat(value)
