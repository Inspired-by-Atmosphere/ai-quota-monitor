# ai-quota-monitor

把各个 AI 订阅的余额 / 配额 / 用量汇总到一处。

它从你用的每个通道抓取数据，输出一个统一的 JSON，交给任意前端渲染（小屏、
终端脚本、定时任务推送都可以）。只用 Python 标准库，零依赖。

| 通道 | 拿到什么 | 凭据 |
|---|---|---|
| 火山方舟 Coding Plan | 5小时 / 日 / 周 / 月 窗口已用百分比 + 重置时间 | AK/SK（Signature V4） |
| 火山方舟 Agent Plan（AFP） | 各窗口 Quota / Used / 剩余 | AK/SK（Signature V4） |
| DeepSeek 开放平台 | 账户余额 | `DEEPSEEK_API_KEY` |
| OpenCode Go | 5小时 / 周 / 月 消费对 $12 / $30 / $60 的占比 | `OPENCODE_GO_API_KEY` |
| GitHub Copilot | 预留通道（需带 `copilot` scope 的 PAT） | `GITHUB_TOKEN` |

## 输出长什么样

不管接了几个渠道，最终都是同一个规范化 JSON——下面是仓库自带的 `examples/sample-quota.json`（占位数字，不含任何凭据）：

```json
{
  "generated_at": "2026-01-01 12:00:00",
  "channels": [
    {
      "id": "volc-codingplan",
      "name": "Volcengine Ark Coding Plan",
      "state": "ok",
      "status": "Running",
      "windows": [
        { "label": "5h window", "used_pct": 17.1, "reset": "01-01 21:27" },
        { "label": "weekly window", "used_pct": 14.5, "reset": "01-08 00:00" },
        { "label": "monthly window", "used_pct": 21.4, "reset": "01-25 23:59" }
      ]
    }
```

*（节选，完整文件见 `examples/sample-quota.json`。）*

读不到、或者你根本没配的渠道，会如实写成 `state: unavailable` 并附原因——不会伪造一个 0 出来。

## 为什么做这个

订阅制现在都按窗口限流（5小时 / 日 / 周 / 月）。做到一半撞限额很难受，
提前收到一行提醒就不难受。它最初只是"快超了告诉我一声"，后来长成了一块常驻小屏。

## 快速开始

```bash
git clone https://github.com/Inspired-by-Atmosphere/ai-quota-monitor.git
cd ai-quota-monitor
python quota_panel.py --out data/quota.json
```

需要 Python 3.8+，无需安装任何第三方包。

凭据放在 dotenv 文件里（查找顺序：`$QUOTA_ENV_FILE` → `./.env` → `~/.hermes/.env`），
或直接导出环境变量：

```dotenv
# 火山方舟（一个 plan 一对 AK/SK；_2 / _3 后缀 = 更多账号）
VOLC_ARK_AK=你的-ak
VOLC_ARK_SK=你的-sk
VOLC_ARK_AK_2=你的-ak-2
VOLC_ARK_SK_2=你的-sk-2

DEEPSEEK_API_KEY=你的-key
OPENCODE_GO_API_KEY=你的-key
GITHUB_TOKEN=你的-pat        # 可选，Copilot 通道
```

环境变量优先于 dotenv 文件。没配凭据的通道会标成 `no_cred`，不会让整轮跑挂。

## 独立小工具

```bash
python codingplan_usage.py                # 多账号 Coding Plan 报告（人读）
python codingplan_usage.py --warn-only    # 只有超过 60% 才输出一行
python afp_usage.py                       # Agent Plan（AFP）窗口用量
python codingplan_warn.py                 # 等同 --warn-only，供定时任务用
```

都支持 `--env FILE` 指定 dotenv 文件。

## 输出结构

```json
{
  "generated_at": "2026-01-01 12:00:00",
  "channels": [
    {
      "id": "volc-codingplan",
      "name": "Volcengine Ark Coding Plan",
      "state": "ok",
      "status": "Running",
      "windows": [
        { "label": "5h window", "used_pct": 17.1, "reset": "01-01 21:27" }
      ]
    }
  ]
}
```

完整（虚构）示例见 `examples/sample-quota.json`。

## 接到定时任务

```cron
# 只在越过预警线时提醒
*/30 * * * * cd /opt/ai-quota-monitor && python codingplan_warn.py

# 刷新前端读的 JSON
0 */2 * * * cd /opt/ai-quota-monitor && python quota_panel.py --out /var/www/quota.json
```

## 已知局限

- 火山这两个额度接口属于管控面 API，官方并未声明为本用途的稳定公开接口；
  一旦返回结构变动，解析需要跟着改。各通道依赖的字段见 `docs/CHANNELS.md`。
- 数字一律按服务端返回值原样呈现，不做任何估算。
- Copilot 通道需要带 `copilot` scope 的 PAT，否则该通道标 `unavailable`
  （`ghu_` 开头的 GitHub App token 读不了这个接口）。
- 本仓库故意不带前端：它只产 JSON，界面请自带。

## 许可

MIT，见 [LICENSE](LICENSE)。
