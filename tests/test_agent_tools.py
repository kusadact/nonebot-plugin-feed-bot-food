from __future__ import annotations

from nonebot_plugin_feed_bot_food.agent_tools import FEED_BOT_FOOD_INSTRUCTIONS


def test_agent_feed_tool_requires_a_reply_for_every_result() -> None:
    instructions = "\n".join(FEED_BOT_FOOD_INSTRUCTIONS)

    assert "无论返回" in instructions
    assert "都必须继续调用 reply_user 回复用户" in instructions
    assert "只有当用户明确表达投喂意图" in instructions
    assert "无法判断输入是否为食物，不要调用" in instructions
    assert "feed_bot_food 不负责判断食物是否可食用" in instructions
    assert "internal_error 时静默结束本次处理" not in instructions
