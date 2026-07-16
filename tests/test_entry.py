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


def test_status_reply_uses_requested_labels_and_bot_name() -> None:
    reply = format_status_result(
        {
            "current_weight_kg": 48.62,
            "today_feed_count": 0,
            "today_gain_kg": 0.00,
            "yesterday_feed_count": 33,
            "yesterday_gain_kg": 1.25,
            "yesterday_weight_change_kg": 2.50,
            "total_feed_count": 49,
            "total_gain_kg": 12.34,
        },
        "饭团",
    )
    assert reply.splitlines() == [
        "饭团当前体重：97.24斤",
        "今日投喂次数：0",
        "今日累计摄入：0.00斤",
        "昨日投喂次数：33",
        "昨日体重变化：+5.00斤",
        "昨日累计摄入：2.50斤",
        "历史投喂次数：49",
        "历史累计摄入：24.68斤",
    ]


def test_unknown_feed_result_still_has_a_user_facing_message() -> None:
    assert format_feed_result({"status": "unexpected"}) == "投喂失败。"


def test_empty_feed_has_a_user_facing_error() -> None:
    assert format_feed_result({"status": "invalid_food"}) == "请提供要投喂的食物。"


def test_success_feed_reports_random_gain() -> None:
    reply = format_feed_result(
        {
            "status": "success",
            "food": "汉堡",
            "gain_kg": 1.0,
            "today_gain_kg": 1.0,
        }
    )
    assert reply == "投喂汉堡成功，今天一共吃了 1.00kg。"


@pytest.mark.asyncio
async def test_commands_only_accept_group_messages_without_mention_requirement() -> None:
    event = fake_group_event(Message("/投喂汉堡"))
    assert await _group_only(event)

    status_event = fake_group_event(Message("/查看状态"))
    assert await _group_only(status_event)
