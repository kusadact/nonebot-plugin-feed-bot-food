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
                "- feed_bot_food 返回 non_edible 时必须回复用户该食物不可食用；这是正常业务结果，不能静默。",
                "- feed_bot_food 返回 ignored 时必须依据 message 告知用户未进行投喂；这是正常业务结果，不能静默。",
                "- feed_bot_food 返回 success 时依据返回字段回复；若 too_much 为 true，必须告知用户实际吃了多少（使用 gain_kg），措辞由 Agent 自然组织，不要套用固定句式。",
                "- feed_bot_food 返回 category_limited、request_limited 或 invalid_food 时，依据返回的 message 和字段向用户回复；不要重复调用工具。",
                "- feed_bot_food 返回 llm_error 时静默结束本次处理，不要向用户发送消息；这是分类或请求失败。",
                "- 工具只处理体重和投喂数据，最终回复由 Agent 根据自身规则生成。",
            ],
            tool_limits=[
                ToolLimitSpec(tool_name="feed_bot_food", run_limit=1),
                ToolLimitSpec(tool_name="get_feed_bot_status", run_limit=1),
            ],
        )

    return True
