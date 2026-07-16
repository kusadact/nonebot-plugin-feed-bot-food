from __future__ import annotations

from nonebot_plugin_feed_bot_food.agent_tools import FEED_BOT_FOOD_INSTRUCTIONS


def test_agent_feed_tool_requires_a_reply_for_every_result() -> None:
    instructions = "\n".join(FEED_BOT_FOOD_INSTRUCTIONS)

    assert "可以吃的食物或可以喝的饮料" in instructions
    assert "明显不能吃或不能喝" in instructions
    assert "今天一共吃了多少" in instructions
    assert "工具只处理体重和投喂数据，最终回复由 Agent 根据自身规则生成。" in instructions
