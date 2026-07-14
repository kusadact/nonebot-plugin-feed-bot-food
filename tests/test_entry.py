from __future__ import annotations

import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from pydantic import create_model

from nonebot_plugin_feed_bot_food.entry import _group_only, format_feed_result, format_status_result


def fake_group_event(message: Message):
    from nonebot.adapters.onebot.v11.event import Sender

    fake = create_model("FakeGroupEvent", __base__=GroupMessageEvent)
    return fake(
        time=1,
        self_id=1,
        post_type="message",
        sub_type="normal",
        user_id=2,
        message_type="group",
        group_id=3,
        message_id=4,
        message=message,
        raw_message=str(message),
        font=0,
        sender=Sender(card="", nickname="user", role="member"),
        to_me=True,
    )


def test_status_reply_has_only_requested_fields() -> None:
    reply = format_status_result(
        {
            "current_weight_kg": 48.62,
            "today_feed_count": 2,
            "today_gain_kg": 0.72,
            "total_feed_count": 8,
        }
    )
    assert reply.splitlines() == [
        "当前体重：48.62kg",
        "今日成功投喂次数：2",
        "今日累计增加体重：0.72kg",
        "历史成功投喂总次数：8",
    ]


def test_unknown_feed_has_a_user_facing_message() -> None:
    assert format_feed_result({"status": "ignored"}) == "无法确认这个食物的分类，未进行投喂。"


def test_llm_error_has_a_user_facing_message() -> None:
    assert format_feed_result({"status": "llm_error", "message": "上游失败"}) == "上游失败"


def test_llm_error_without_message_has_a_fallback_reply() -> None:
    assert format_feed_result({"status": "llm_error"}) == "投喂暂时失败，请稍后再试。"


def test_unknown_feed_result_still_has_a_user_facing_message() -> None:
    assert format_feed_result({"status": "unexpected"}) == "投喂失败。"


def test_empty_feed_has_a_user_facing_error() -> None:
    assert format_feed_result({"status": "invalid_food"}) == "请提供要投喂的食物。"


def test_non_edible_feed_has_a_user_facing_message() -> None:
    assert format_feed_result({"status": "non_edible", "food": "猫薄荷"}) == "猫薄荷不可食用。"


def test_over_limit_feed_reports_actual_consumed_amount() -> None:
    reply = format_feed_result(
        {
            "status": "success",
            "food": "方便面",
            "gain_kg": 1.0,
            "current_weight_kg": 49.0,
            "too_much": True,
        }
    )
    assert reply == "本次实际吃了 1.00kg，当前体重 49.00kg。"


@pytest.mark.asyncio
async def test_commands_only_accept_group_messages_without_mention_requirement() -> None:
    event = fake_group_event(Message("/投喂汉堡"))
    assert await _group_only(event)

    status_event = fake_group_event(Message("/查看状态"))
    assert await _group_only(status_event)
