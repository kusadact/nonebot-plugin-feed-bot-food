from __future__ import annotations

import json

from .service import FeedService


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
            """投喂一种食物，并返回分类、增加体重和当前体重。"""
            result = await service.feed(ctx.bot_id or "", ctx.user_id or "", food)
            return json.dumps(result, ensure_ascii=False)

        @tool("get_feed_bot_status")
        async def get_feed_bot_status() -> str:
            """获取当前 Bot 的体重、今日投喂次数、今日增重和历史投喂总次数。"""
            result = await service.get_status(ctx.bot_id or "")
            return json.dumps(result, ensure_ascii=False)

        return AgentToolBundle(
            name="feed_bot_food",
            tools=[feed_bot_food, get_feed_bot_status],
            instructions=[
                "- 用户明确要投喂食物时调用 feed_bot_food。",
                "- 用户询问当前体重或投喂统计时调用 get_feed_bot_status。",
                "- 工具返回 ignored 时不要回复，直接结束本次处理。",
                "- 工具只处理体重和投喂数据，最终回复由 Agent 根据自身规则生成。",
            ],
            tool_limits=[
                ToolLimitSpec(tool_name="feed_bot_food", run_limit=1),
                ToolLimitSpec(tool_name="get_feed_bot_status", run_limit=1),
            ],
        )

    return True
