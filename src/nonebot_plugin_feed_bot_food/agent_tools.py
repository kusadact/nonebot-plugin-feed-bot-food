from __future__ import annotations

import json
from typing import Any

from .service import FeedService

FEED_BOT_FOOD_INSTRUCTIONS = (
    "- 只有当用户明确想让 Bot 吃东西，并且输入看起来是可以吃的食物或可以喝的饮料时，才调用 feed_bot_food。",
    "- 如果输入明显不能吃或不能喝，例如石头、手机等，直接拒绝，不要调用 feed_bot_food。",
    "- 如果只是闲聊、提问、举例，或无法判断能不能吃，不要调用 feed_bot_food。",
    "- 只要调用了工具，就必须调用 reply_user 回复用户，不能静默结束。",
    "- 投喂成功后，用 today_gain_kg 告诉用户今天一共吃了多少；不要提当前体重，体重会在第二天 06:00 结算。",
    "- 用户询问当前体重或投喂统计时调用 get_feed_bot_status。",
    "- 其他工具结果直接根据 message 回复，不要重复调用工具。",
)


def _agent_feed_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep the feed tool focused on today's intake instead of unsettled weight."""
    if result.get("status") != "success":
        return result
    result = dict(result)
    result.pop("current_weight_kg", None)
    return result


def register_agent_tools(service: FeedService) -> bool:
    """Register optional groupmate-agent tools without making it a hard dependency."""
    try:
        from nonebot import require

        require("nonebot_plugin_groupmate_agent")
        from langchain.tools import tool
        from nonebot_plugin_groupmate_agent.agent import AgentToolBundle, AgentToolContext, register_agent_tool
        from nonebot_plugin_groupmate_agent.agent.optional_tools import ToolLimitSpec
    except (ImportError, RuntimeError):
        return False

    @register_agent_tool
    def build_feed_bot_food_tools(ctx: AgentToolContext) -> AgentToolBundle | None:
        if ctx.is_private or not ctx.bot_id or not ctx.user_id:
            return None

        @tool("feed_bot_food")
        async def feed_bot_food(food: str) -> str:
            """投喂一种食物，并返回今天累计吃了多少。"""
            try:
                result = await service.feed(ctx.bot_id or "", ctx.user_id or "", food)
            except Exception:
                result = {
                    "status": "internal_error",
                    "food": food.strip(),
                    "message": "投喂暂时失败，请稍后再试。",
                    "reply_required": True,
                }
            return json.dumps(_agent_feed_result(result), ensure_ascii=False)

        @tool("get_feed_bot_status")
        async def get_feed_bot_status() -> str:
            """获取当前 Bot 的体重、今日和昨日投喂统计及历史投喂总次数。"""
            result = await service.get_status(ctx.bot_id or "")
            return json.dumps(result, ensure_ascii=False)

        return AgentToolBundle(
            name="feed_bot_food",
            tools=[feed_bot_food, get_feed_bot_status],
            instructions=FEED_BOT_FOOD_INSTRUCTIONS,
            tool_limits=[
                ToolLimitSpec(tool_name="feed_bot_food", run_limit=1),
                ToolLimitSpec(tool_name="get_feed_bot_status", run_limit=1),
            ],
        )

    return True
