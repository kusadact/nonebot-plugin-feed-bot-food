from __future__ import annotations

import json

from .service import FeedService

FEED_BOT_FOOD_INSTRUCTIONS = (
    "- 用户明确要投喂食物时调用 feed_bot_food。",
    "- 只要调用了 feed_bot_food，就视为已经处理了用户投喂；无论返回 success、non_edible、ignored、total_limited、request_limited、llm_error 还是 internal_error，都必须继续调用 reply_user 回复用户，不能调用 finish 后静默。",
    "- feed_bot_food 返回 non_edible 时必须依据 message 回复用户该食物不可食用；这是正常业务结果，不能静默。",
    "- feed_bot_food 返回 ignored 时必须依据 message 告知用户未进行投喂；这是正常业务结果，不能静默。",
    "- feed_bot_food 返回 success 时依据返回字段回复；若 too_much 为 true，必须告知用户实际吃了多少（使用 gain_kg），措辞由 Agent 自然组织，不要套用固定句式。",
    "- feed_bot_food 返回 total_limited、request_limited 或 invalid_food 时，依据返回的 message 和字段向用户回复；不要重复调用工具。",
    "- feed_bot_food 返回 llm_error 或 internal_error 时，必须依据 message 告知用户本次投喂未完成；不要静默结束本次处理。",
    "- feed_bot_food 返回未知状态时，也必须通过 reply_user 告知用户投喂暂时失败。",
    "- 用户询问当前体重或投喂统计时调用 get_feed_bot_status。",
    "- 工具只处理体重和投喂数据，最终回复由 Agent 根据自身规则生成。",
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
            """投喂一种食物，并返回分类、增加体重和当前体重。"""
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
            """获取当前 Bot 的体重、今日投喂次数、今日增重和历史投喂总次数。"""
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
