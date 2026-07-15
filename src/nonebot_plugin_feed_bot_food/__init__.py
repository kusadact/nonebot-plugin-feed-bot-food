"""投喂 Bot 食物的 NoneBot 插件。"""

from __future__ import annotations

import importlib.util

from nonebot import get_plugin_config, logger, require
from nonebot.plugin import PluginMetadata

from .agent_tools import register_agent_tools
from .classifier import FoodClassifier
from .config import Config
from .entry import register_matchers
from .scheduler import register_scheduler
from .service import FeedService
from .storage import JsonStateStore

__version__ = "0.1.8"

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-feed-bot-food",
    description="投喂 Bot 食物并维护体重",
    usage="群聊中使用 /投喂<食物>；/查看体重或 /查看状态",
    type="application",
    config=Config,
    supported_adapters={"~onebot.v11"},
)


plugin_config = get_plugin_config(Config).feed_bot_food
state_store = JsonStateStore()
classifier = FoodClassifier(plugin_config)
feed_service = FeedService(plugin_config, state_store, classifier)

register_matchers(feed_service)
register_scheduler(feed_service)

if plugin_config.enable_groupmate_agent:
    try:
        if importlib.util.find_spec("nonebot_plugin_groupmate_agent") is not None:
            require("nonebot_plugin_groupmate_agent")
            if register_agent_tools(feed_service):
                logger.info("已注册 groupmate-agent 投喂工具")
    except Exception:
        logger.warning("groupmate-agent 不可用，跳过投喂工具注册")
