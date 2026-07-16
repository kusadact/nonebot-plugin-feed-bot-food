# nonebot-plugin-feed-bot-food

一个通过 OneBot 投喂 Bot 食物并维护体重的 NoneBot2 插件。

兼容 Python `3.10` 到 `3.13`，使用 `uv` 管理依赖。

## 安装

```bash
uv add nonebot-plugin-feed-bot-food
```

将插件加入 NoneBot 配置的插件列表，并确保使用 OneBot V11 适配器。

## 配置

配置使用 `feed_bot_food__` 前缀。下面是默认配置：

```dotenv
FEED_BOT_FOOD__INITIAL_WEIGHT=48.00
FEED_BOT_FOOD__METABOLIC_CONSTANT=5.00
FEED_BOT_FOOD__METABOLIC_POWER=2.00
FEED_BOT_FOOD__WINDOW_HOURS=6
FEED_BOT_FOOD__CATEGORY_LIMITS=3
FEED_BOT_FOOD__RANDOM_GAIN_RANGE=[0.05, 1.00]
FEED_BOT_FOOD__ENABLE_GROUPMATE_AGENT=true
```

- `INITIAL_WEIGHT`：首次创建某个 Bot 状态时的初始体重，默认 `48.00kg`。
- `METABOLIC_CONSTANT`：标准体重下的基础代谢阈值 `M`，默认 `5.00`。它和每日食物增重使用相同单位。
- `METABOLIC_POWER`：基础代谢阈值中的非线性指数 `p`，默认 `2.00`。
- `WINDOW_HOURS`：固定投喂窗口长度，默认 6 小时。
- `CATEGORY_LIMITS`：每名用户每个窗口所有类别合计的成功投喂次数，默认 3 次。虽然配置名沿用旧名称，但值现在是单个整数。
- `RANDOM_GAIN_RANGE`：每次成功投喂随机增加的体重范围，默认 `0.05～1.00kg`。
- `ENABLE_GROUPMATE_AGENT`：是否注册 Agent Tool，默认开启；groupmate-agent 不可用时自动跳过。

最低体重固定为 `0.00kg`，每天 Asia/Shanghai 时间 `06:00` 结算昨日体重，不作为配置项。

## 群聊命令

只处理群聊，使用标准 NoneBot 命令，不需要 `@Bot`：

```text
/投喂汉堡
/查看体重
/查看状态
```

状态只展示：

- Bot 名称和当前体重
- 今日投喂次数
- 今日累计摄入
- 昨日投喂次数
- 昨日体重变化（摄入和基础代谢结算后的实际变化）
- 昨日累计摄入
- 历史投喂次数
- 历史累计摄入

状态查询中的当前体重不包含今日累计摄入；体重、今日累计摄入、昨日累计摄入、历史累计摄入和昨日净体重变化以斤展示，内部计算和数据存储仍使用 kg；换算比例为 `1kg=2斤`。

私聊不会触发这些命令；`/查看体重` 和 `/查看状态` 是同一个命令的两个名称。

## 投喂规则

Agent 会在调用投喂工具前，根据用户意图判断输入是否像食物或饮料；闲聊、提问、举例或无法判断时不会调用工具。工具被调用后，插件使用 Python 随机数在 `RANDOM_GAIN_RANGE` 内生成本次增加的体重。直接 `/投喂` 命令不进行食物分类，非空输入即可进入投喂流程。

“今日”统计区间为 Asia/Shanghai 时间 `06:00` 至次日 `05:59:59`。固定窗口默认是 `06-12`、`12-18`、`18-00`、`00-06`。

每个用户每个窗口按所有类别合计限制成功投喂次数。窗口到达边界后立即刷新额度，不再设置边界保护区或顺延分类槽位。

只要投喂请求已经进入插件，成功、限流、参数错误和服务失败都会返回一条用户可见提示，不会静默结束。

每日结算公式为：

```text
a = M × (当前体重 / 初始体重)^p
d = 昨日实际摄入 - a
体重变化 = 7.8541 × sign(d) × (1 - exp(-|d| / 20.7809))
结算后体重 = 当前体重 + 体重变化
```

其中 `M` 由 `METABOLIC_CONSTANT` 配置，默认 `5.00`，`p` 由 `METABOLIC_POWER` 配置，默认 `2.00`；公式中的 `7.8541` 和 `20.7809` 是插件内置的模型参数，不作为配置项。摄入量超过代谢阈值后，体重增加会逐渐趋于饱和；摄入不足时则会减重。

结算后体重不会低于 `0.00kg`。Bot 离线时，重新连接后会补做尚未结算的日期，且同一天只结算一次。

## groupmate-agent 集成

插件通过 groupmate-agent 的注册接口提供两个 Tool：

- `feed_bot_food(food)`：执行投喂并返回今天累计吃了多少；当前体重通过次日结算更新。
- `get_feed_bot_status()`：返回当前体重、今日和昨日投喂统计及历史总次数。

Tool 只返回结构化 JSON，不直接发送 OneBot 消息；只有用户明确想让 Bot 吃东西，且输入看起来是可以吃的食物或可以喝的饮料时，Agent 才应调用 `feed_bot_food`。明显不能吃或不能喝的内容应直接拒绝，不调用工具。只要 `feed_bot_food` 已被调用，Agent 必须依据结果调用 `reply_user` 回复，不能调用 `finish` 后静默。Agent Tool 只在群聊上下文提供，groupmate-agent 未安装、未加载或集成关闭时，直接群聊命令仍可用。

## 数据文件

状态保存在 NoneBot 插件标准数据目录的 `state.json` 中。数据按 Bot ID 分区，使用原子写入和进程内锁保护并发更新。

当前状态文件格式为 schema v3。首次读取 schema v1 或 v2 文件时，插件会自动补齐每日体重变化字段，并移除旧 LLM 投喂事件中的 `category` 和 `user_attempts` 字段，然后原子写回 v3。

## 开发

```bash
uv sync
uv run pytest
uv run ruff check src tests
```
