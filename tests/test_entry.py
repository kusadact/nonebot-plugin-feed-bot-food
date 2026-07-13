from __future__ import annotations

import pytest
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from pydantic import create_model

from nonebot_plugin_feed_bot_food.entry import _feed_rule, _status_rule, format_feed_result, format_status_result


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


def test_unknown_feed_is_silent() -> None:
    assert format_feed_result({"status": "ignored"}) is None


def test_empty_feed_has_a_user_facing_error() -> None:
    assert format_feed_result({"status": "invalid_food"}) == "请提供要投喂的食物。"


@pytest.mark.asyncio
async def test_commands_require_bot_mention_and_group_message() -> None:
    bot = Bot(None, "1")
    event = fake_group_event(Message([MessageSegment.at("1"), MessageSegment.text(" 投喂汉堡")]))
    assert await _feed_rule(bot, event)
    assert not await _status_rule(bot, event)

    empty_feed = fake_group_event(Message([MessageSegment.at("1"), MessageSegment.text(" 投喂")]))
    assert await _feed_rule(bot, empty_feed)

    status_event = fake_group_event(Message([MessageSegment.at("1"), MessageSegment.text(" 查看投喂状态")]))
    assert await _status_rule(bot, status_event)

    unmentioned = fake_group_event(Message("投喂汉堡"))
    assert not await _feed_rule(bot, unmentioned)
