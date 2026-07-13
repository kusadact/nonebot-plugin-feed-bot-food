from __future__ import annotations

from nonebot import get_bots, get_driver, logger
from nonebot.adapters import Bot
from nonebot_plugin_apscheduler import scheduler

from .service import FeedService


def register_scheduler(service: FeedService) -> None:
    @scheduler.scheduled_job(
        "cron",
        hour=6,
        minute=0,
        max_instances=1,
        coalesce=True,
        id="feed_bot_food_daily_decay",
    )
    async def daily_decay() -> None:
        for bot_id in list(get_bots()):
            try:
                await service.settle(str(bot_id))
            except Exception:
                logger.exception(f"投喂 Bot 每日减重结算失败: bot_id={bot_id}")

    @get_driver().on_bot_connect
    async def on_bot_connect(bot: Bot) -> None:
        await service.settle(str(bot.self_id))
