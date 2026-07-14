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
FEED_BOT_FOOD__CATEGORY_GAIN_RANGES=[[0.30, 1.00], [0.05, 0.30], [0.10, 0.50]]
FEED_BOT_FOOD__GAIN_RANGE_FLUCTUATION=0.15
FEED_BOT_FOOD__ENABLE_GROUPMATE_AGENT=true
FEED_BOT_FOOD__LLM_BASE_URL=https://api.openai.com/v1
FEED_BOT_FOOD__LLM_API_KEY=
FEED_BOT_FOOD__LLM_MODEL=
```

- `INITIAL_WEIGHT`：首次创建某个 Bot 状态时的初始体重，默认 `48.00kg`。
- `METABOLIC_CONSTANT`：标准体重下的基础代谢阈值 `M`，默认 `5.00`。它和每日食物增重使用相同单位。
- `METABOLIC_POWER`：基础代谢阈值中的非线性指数 `p`，默认 `2.00`。
- `WINDOW_HOURS`：固定投喂窗口长度，默认 6 小时。
- `CATEGORY_LIMITS`：每名用户每个窗口所有类别合计的成功投喂次数，默认 3 次。虽然配置名沿用旧名称，但值现在是单个整数。
- `CATEGORY_GAIN_RANGES`：LLM 返回的三类食物增重范围，单位为 kg。
- `GAIN_RANGE_FLUCTUATION`：每次分类时对三类增重范围上下限分别施加的随机浮动，默认 `0.15kg`。
- `ENABLE_GROUPMATE_AGENT`：是否注册 Agent Tool，默认开启；groupmate-agent 不可用时自动跳过。
- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`：OpenAI 兼容的食物分类接口。缺少任一项时插件仍能加载，但投喂不会修改体重，并会返回配置提示。

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

状态查询中的体重、今日累计摄入、昨日累计摄入和昨日净体重变化以斤展示，内部计算和数据存储仍使用 kg；换算比例为 `1kg=2斤`。

私聊不会触发这些命令；`/查看体重` 和 `/查看状态` 是同一个命令的两个名称。

## 投喂规则

食物交给 OpenAI 兼容 LLM 判断为正餐、水、甜品/小食或不可食用，并要求返回 JSON 分类和增重值。插件会校验并限制增重值在对应配置范围内。

LLM 还会识别输入中的数量和重量。超过对应类别的单次上限时，返回 `too_much=true` 并把本次增重限制在最大值；Agent 会根据实际增重值自行组织回复。

“今日”统计区间为 Asia/Shanghai 时间 `06:00` 至次日 `05:59:59`。固定窗口默认是 `06-12`、`12-18`、`18-00`、`00-06`。

每个用户每个窗口按所有类别合计限制成功投喂次数。窗口到达边界后立即刷新额度，不再设置边界保护区或顺延分类槽位。

每名用户每窗口发送给 LLM 的请求数上限为：

```text
ceil(CATEGORY_LIMITS × 1.5)
```

例如 `CATEGORY_LIMITS=3` 时，每个窗口最多向 LLM 发起 5 次请求。成功、不可食用、无法分类以及 LLM 请求失败都会计入这个请求上限；达到上限后不会再请求 LLM。

只要投喂请求已经进入插件，成功、不可食用、无法分类、限流、配置错误和服务失败都会返回一条用户可见提示，不会静默结束。

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

- `feed_bot_food(food)`：执行投喂并返回分类、增重和当前体重。
- `get_feed_bot_status()`：返回当前体重、今日和昨日投喂统计及历史总次数。

Tool 只返回结构化 JSON，不直接发送 OneBot 消息；只要 `feed_bot_food` 已被调用，Agent 必须依据结果调用 `reply_user` 回复，不能调用 `finish` 后静默。Agent Tool 只在群聊上下文提供，groupmate-agent 未安装、未加载或集成关闭时，直接群聊命令仍可用。若 Agent 宿主在工具调用前就判定普通消息无需参与，则不会发生投喂，也不属于插件已处理的投喂请求。

## 数据文件

状态保存在 NoneBot 插件标准数据目录的 `state.json` 中。数据按 Bot ID 分区，使用原子写入和进程内锁保护并发更新。

当前状态文件格式为 schema v2。首次读取 schema v1 文件时，插件会补齐每日体重变化字段并立即原子写回 v2；后续版本将移除对 schema v1 的兼容。

## 开发

```bash
uv sync
uv run pytest
uv run ruff check src tests
```
