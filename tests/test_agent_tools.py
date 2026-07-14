from __future__ import annotations

from nonebot_plugin_feed_bot_food.agent_tools import FEED_BOT_FOOD_INSTRUCTIONS


def test_agent_feed_tool_requires_a_reply_for_every_result() -> None:
    instructions = "\n".join(FEED_BOT_FOOD_INSTRUCTIONS)

    assert "无论返回" in instructions
    assert "都必须继续调用 reply_user 回复用户" in instructions
    assert "llm_error 或 internal_error" in instructions
    assert "llm_error 时静默结束本次处理" not in instructions
