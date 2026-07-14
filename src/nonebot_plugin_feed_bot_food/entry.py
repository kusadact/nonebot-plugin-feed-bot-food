from __future__ import annotations

from typing import Any

from nonebot import logger, on_command
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from .service import FeedService

KG_TO_JIN = 2.0


async def _group_only(event: Event) -> bool:
    return isinstance(event, GroupMessageEvent)


def register_matchers(service: FeedService) -> None:
    feed_matcher = on_command("投喂", rule=_group_only, priority=5, block=True)
    status_matcher = on_command(
        "查看体重",
        rule=_group_only,
        aliases={"查看状态"},
        priority=5,
        block=True,
    )

    @feed_matcher.handle()
    async def handle_feed(
        bot: Bot,
        event: GroupMessageEvent,
        matcher: Matcher,
        args: Message = CommandArg(),
    ) -> None:
        food = args.extract_plain_text().strip()
        try:
            result = await service.feed(str(bot.self_id), str(event.user_id), food)
        except Exception:
            logger.exception("投喂命令处理失败")
            result = {
                "status": "internal_error",
                "message": "投喂暂时失败，请稍后再试。",
            }
        await matcher.finish(format_feed_result(result))

    @status_matcher.handle()
    async def handle_status(bot: Bot, event: GroupMessageEvent, matcher: Matcher) -> None:
        result = await service.get_status(str(bot.self_id))
        try:
            login_info = await bot.call_api("get_login_info")
        except Exception:
            logger.warning(f"获取 Bot 昵称失败，使用 Bot ID: {bot.self_id}")
            bot_name = str(bot.self_id)
        else:
            bot_name = (
                str(login_info.get("nickname") or bot.self_id)
                if isinstance(login_info, dict)
                else str(bot.self_id)
            )
        await matcher.finish(format_status_result(result, bot_name))


def format_feed_result(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "ignored":
        return str(result.get("message", "无法确认这个食物的分类，未进行投喂。"))
    if status == "llm_error":
        return str(result.get("message", "投喂暂时失败，请稍后再试。"))
    if status == "success":
        if result.get("too_much"):
            return (
                f"本次实际吃了 {float(result['gain_kg']):.2f}kg，"
                f"当前体重 {float(result['current_weight_kg']):.2f}kg。"
            )
        return (
            f"投喂{result['food']}成功，增加 {float(result['gain_kg']):.2f}kg，"
            f"当前体重 {float(result['current_weight_kg']):.2f}kg。"
        )
    if status == "non_edible":
        return f"{result['food']}不可食用。"
    if status == "invalid_food":
        return "请提供要投喂的食物。"
    if status in {"request_limited", "total_limited"}:
        return str(result.get("message", "投喂暂时不可用。"))
    if status == "internal_error":
        return str(result.get("message", "投喂暂时失败，请稍后再试。"))
    return str(result.get("message", "投喂失败。"))


def format_status_result(result: dict[str, Any], bot_name: str = "") -> str:
    current_weight = float(result["current_weight_kg"]) * KG_TO_JIN
    today_gain = float(result["today_gain_kg"]) * KG_TO_JIN
    yesterday_gain = float(result["yesterday_gain_kg"]) * KG_TO_JIN
    yesterday_change = float(result["yesterday_weight_change_kg"]) * KG_TO_JIN
    formatted_yesterday_change = (
        f"{yesterday_change:.2f}" if yesterday_change == 0 else f"{yesterday_change:+.2f}"
    )
    return "\n".join(
        [
            f"{bot_name}当前体重：{current_weight:.2f}斤",
            f"今日投喂次数：{int(result['today_feed_count'])}",
            f"今日累计摄入：{today_gain:.2f}斤",
            f"昨日投喂次数：{int(result['yesterday_feed_count'])}",
            f"昨日体重变化：{formatted_yesterday_change}斤",
            f"昨日累计摄入：{yesterday_gain:.2f}斤",
            f"历史投喂次数：{int(result['total_feed_count'])}",
        ]
    )
