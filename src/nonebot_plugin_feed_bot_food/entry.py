from __future__ import annotations

import re
from typing import Any

from nonebot import on_message
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.matcher import Matcher

from .service import FeedService

FEED_PATTERN = re.compile(r"^\s*投喂\s*(?P<food>.+?)\s*$")
STATUS_PATTERN = re.compile(r"^\s*(?:查看|查询)\s*(?:体重|投喂)(?:\s*状态)?\s*$")


def _is_bot_mentioned(bot: Bot, event: GroupMessageEvent) -> bool:
    bot_id = str(bot.self_id)
    return any(
        segment.type == "at" and str(segment.data.get("qq", "")) == bot_id
        for segment in event.get_message()
    )


def _plain_text(event: GroupMessageEvent) -> str:
    return event.get_message().extract_plain_text().strip()


async def _feed_rule(bot: Bot, event: Event) -> bool:
    return isinstance(event, GroupMessageEvent) and _is_bot_mentioned(bot, event) and bool(
        FEED_PATTERN.fullmatch(_plain_text(event))
    )


async def _status_rule(bot: Bot, event: Event) -> bool:
    return isinstance(event, GroupMessageEvent) and _is_bot_mentioned(bot, event) and bool(
        STATUS_PATTERN.fullmatch(_plain_text(event))
    )


def register_matchers(service: FeedService) -> None:
    feed_matcher = on_message(rule=_feed_rule, priority=5, block=True)
    status_matcher = on_message(rule=_status_rule, priority=5, block=True)

    @feed_matcher.handle()
    async def handle_feed(bot: Bot, event: GroupMessageEvent, matcher: Matcher) -> None:
        match = FEED_PATTERN.fullmatch(_plain_text(event))
        if match is None:
            return
        result = await service.feed(str(bot.self_id), str(event.user_id), match.group("food"))
        reply = format_feed_result(result)
        if reply is not None:
            await matcher.finish(reply)

    @status_matcher.handle()
    async def handle_status(bot: Bot, event: GroupMessageEvent, matcher: Matcher) -> None:
        result = await service.get_status(str(bot.self_id))
        await matcher.finish(format_status_result(result))


def format_feed_result(result: dict[str, Any]) -> str | None:
    status = result.get("status")
    if status == "ignored":
        return None
    if status == "success":
        return (
            f"投喂{result['food']}成功，增加 {float(result['gain_kg']):.2f}kg，"
            f"当前体重 {float(result['current_weight_kg']):.2f}kg。"
        )
    if status == "non_edible":
        return f"{result['food']}不可食用。"
    if status == "invalid_food":
        return "请提供要投喂的食物。"
    if status in {"request_limited", "category_limited", "llm_error"}:
        return str(result.get("message", "投喂暂时不可用。"))
    return str(result.get("message", "投喂失败。"))


def format_status_result(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"当前体重：{float(result['current_weight_kg']):.2f}kg",
            f"今日成功投喂次数：{int(result['today_feed_count'])}",
            f"今日累计增加体重：{float(result['today_gain_kg']):.2f}kg",
            f"历史成功投喂总次数：{int(result['total_feed_count'])}",
        ]
    )
