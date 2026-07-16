from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import FeedBotFoodConfig
from .models import BotState, FeedEvent

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


def _is_in_window(event: FeedEvent, start: datetime, end: datetime) -> bool:
    event_time = localize(event.timestamp)
    return start <= event_time < end


def feed_count_in_window(
    state: BotState,
    user_id: str,
    moment: datetime,
    config: FeedBotFoodConfig,
) -> int:
    moment = localize(moment)
    start = window_start(moment, config.window_hours)
    end = start + timedelta(hours=config.window_hours)
    return sum(
        1
        for event in state.events
        if event.user_id == user_id and _is_in_window(event, start, end)
    )


def feed_available(
    state: BotState,
    user_id: str,
    moment: datetime,
    config: FeedBotFoodConfig,
) -> bool:
    return feed_count_in_window(state, user_id, moment, config) < config.category_limits


def next_feed_retry(moment: datetime, config: FeedBotFoodConfig) -> datetime:
    return window_end(moment, config.window_hours)


def prune_state(state: BotState, moment: datetime) -> None:
    moment = localize(moment)
    event_cutoff = moment - timedelta(days=3)
    state.events = [event for event in state.events if localize(event.timestamp) >= event_cutoff]


def date_from_key(value: str) -> date:
    return date.fromisoformat(value)
