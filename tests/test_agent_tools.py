from __future__ import annotations

from nonebot_plugin_feed_bot_food.agent_tools import (
    FEED_BOT_FOOD_INSTRUCTIONS,
    _agent_feed_result,
)


def test_agent_feed_tool_requires_a_reply_for_every_result() -> None:
    instructions = "\n".join(FEED_BOT_FOOD_INSTRUCTIONS)

    assert "可以吃的食物或可以喝的饮料" in instructions
    assert "明显不能吃或不能喝" in instructions
    assert "今天一共吃了多少" in instructions
    assert "不要提当前体重" in instructions


def test_agent_feed_result_hides_unsettled_weight() -> None:
    result = _agent_feed_result(
        {
            "status": "success",
            "gain_kg": 0.62,
            "today_gain_kg": 1.24,
            "current_weight_kg": 48.00,
        }
    )

    assert result == {
        "status": "success",
        "gain_kg": 0.62,
        "today_gain_kg": 1.24,
    }
