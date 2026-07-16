from __future__ import annotations

import json

from .service import FeedService

FEED_BOT_FOOD_INSTRUCTIONS = (
    "- 只有当用户明确表达投喂意图，并且输入看起来是食物或饮料时，才调用 feed_bot_food。",
    "- 如果用户只是闲聊、提问、举例，或无法判断输入是否为食物，不要调用 feed_bot_food。",
    "- 一旦调用了 feed_bot_food，就视为已经处理了用户投喂；无论返回 success、total_limited、invalid_food 还是 internal_error，都必须继续调用 reply_user 回复用户，不能调用 finish 后静默。",
    "- feed_bot_food 不负责判断食物是否可食用；是否调用工具由 Agent 根据上下文判断。",
    "- feed_bot_food 返回 success 时依据 gain_kg 和 current_weight_kg 回复用户，措辞由 Agent 自然组织。",
    "- feed_bot_food 返回 total_limited 或 invalid_food 时，依据返回的 message 回复；不要重复调用工具。",
    "- feed_bot_food 返回 internal_error 时，必须依据 message 告知用户本次投喂未完成；不要静默结束本次处理。",
    "- 工具只处理体重和投喂数据，最终回复由 Agent 根据自身规则生成。",
    "- 用户询问当前体重或投喂统计时调用 get_feed_bot_status。",
)


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
            """投喂一种食物，并返回增加体重和当前体重。"""
            try:
                result = await service.feed(ctx.bot_id or "", ctx.user_id or "", food)
            except Exception:
                result = {
                    "status": "internal_error",
                    "food": food.strip(),
                    "message": "投喂暂时失败，请稍后再试。",
                    "reply_required": True,
                }
            return json.dumps(result, ensure_ascii=False)

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
