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
FEED_BOT_FOOD__WINDOW_HOURS=6
FEED_BOT_FOOD__CATEGORY_LIMITS=[1, 1, 1]
FEED_BOT_FOOD__CATEGORY_GAIN_RANGES=[[0.30, 1.00], [0.05, 0.30], [0.10, 0.50]]
FEED_BOT_FOOD__GAIN_RANGE_FLUCTUATION=0.15
FEED_BOT_FOOD__DECAY_FLUCTUATION=0.10
FEED_BOT_FOOD__ENABLE_GROUPMATE_AGENT=true
FEED_BOT_FOOD__LLM_BASE_URL=https://api.openai.com/v1
FEED_BOT_FOOD__LLM_API_KEY=
FEED_BOT_FOOD__LLM_MODEL=
```

`CATEGORY_LIMITS` 和 `CATEGORY_GAIN_RANGES` 的顺序都是：正餐、水、甜品/小食。

- `INITIAL_WEIGHT`：首次创建某个 Bot 状态时的初始体重，默认 `48.00kg`。
- `WINDOW_HOURS`：固定投喂窗口长度，默认 6 小时。
- `CATEGORY_LIMITS`：每名用户每个窗口各类食物的成功投喂次数，默认每类 1 次。
- `CATEGORY_GAIN_RANGES`：LLM 返回的三类食物增重范围，单位为 kg。
- `GAIN_RANGE_FLUCTUATION`：每次分类时对三类增重范围上下限分别施加的随机浮动，默认 `0.15kg`。
- `DECAY_FLUCTUATION`：每日减重系数的浮动值，默认 `0.10`，即 `0.85～1.05`。
- `ENABLE_GROUPMATE_AGENT`：是否注册 Agent Tool，默认开启；groupmate-agent 不可用时自动跳过。
- `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`：OpenAI 兼容的食物分类接口。缺少任一项时插件仍能加载，但投喂不会修改体重。

最低体重固定为 `35.00kg`，每天 Asia/Shanghai 时间 `06:00` 结算昨日体重，不作为配置项。

## 群聊命令

只处理群聊，使用标准 NoneBot 命令，不需要 `@Bot`：

```text
/投喂汉堡
/查看体重
/查看状态
```

状态只展示：

- 当前体重
- 今日成功投喂次数
- 今日累计增加体重
- 历史成功投喂总次数

私聊不会触发这些命令；`/查看体重` 和 `/查看状态` 是同一个命令的两个名称。

## 投喂规则

食物交给 OpenAI 兼容 LLM 判断为正餐、水、甜品/小食或不可食用，并要求返回 JSON 分类和增重值。插件会校验并限制增重值在对应配置范围内。

LLM 还会识别输入中的数量和重量。超过对应类别的单次上限时，返回 `too_much=true` 并把本次增重限制在最大值；Agent 会根据实际增重值自行组织回复。

“今日”统计区间为 Asia/Shanghai 时间 `06:00` 至次日 `05:59:59`。固定窗口默认是 `06-12`、`12-18`、`18-00`、`00-06`。

每个用户每个窗口按分类限制成功投喂次数。窗口边界前一小时内使用的分类槽位会顺延 2 小时，例如 `11:38` 投喂正餐后，下一次正餐最早为 `13:38`；未投喂的其他分类仍按 `12:00` 正常刷新。

每名用户每窗口发送给 LLM 的请求数上限为：

```text
ceil((正餐次数 + 水次数 + 小食次数) × 1.5)
```

成功、不可食用、无法分类以及 LLM 请求失败都会计入这个请求上限；达到上限后不会再请求 LLM。

每日减重公式为：

```text
减重 = 昨日实际增加体重 × random(0.95 - 浮动值, 0.95 + 浮动值)
      × (初始体重 / 当前体重)
```

减重后体重不会低于 `35.00kg`。Bot 离线时，重新连接后会补做尚未结算的日期，且同一天只结算一次。

## groupmate-agent 集成

插件通过 groupmate-agent 的注册接口提供两个 Tool：

- `feed_bot_food(food)`：执行投喂并返回分类、增重和当前体重。
- `get_feed_bot_status()`：返回当前体重、今日投喂次数、今日增重和历史总次数。

Tool 只返回结构化 JSON，不直接发送 OneBot 消息；最终回复由 Agent 根据自身规则生成。Agent Tool 只在群聊上下文提供，groupmate-agent 未安装、未加载或集成关闭时，直接群聊命令仍可用。

## 数据文件

状态保存在 NoneBot 插件标准数据目录的 `state.json` 中。数据按 Bot ID 分区，使用原子写入和进程内锁保护并发更新。

## 开发

```bash
uv sync
uv run pytest
uv run ruff check src tests
```
