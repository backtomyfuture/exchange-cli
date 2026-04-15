---
name: exchange-cli
version: 1.0.0
description: |
  Exchange邮件CLI工具：收发邮件、搜索邮件、管理草稿、查看日历事件、管理任务、查询联系人。
  当用户需要收发Exchange/Outlook邮件、查看日历、管理任务、搜索联系人时使用。
  即使用户只是说"帮我查一下邮件"、"发一封邮件给xxx"、"看看今天有什么会议"，也应该触发。
metadata:
  requires:
    bins: ["exchange-cli"]
  cliHelp: "exchange-cli --help"
---

# exchange-cli 命令参考

exchange-cli 是一个 Exchange Web Services CLI 工具，直接连接 Exchange/Office 365 服务器。

## 安全与执行规则

- 发送邮件前必须向用户确认收件人、主题和正文
- 删除操作（邮件、日历事件、任务）前必须确认
- 不要在输出中暴露密码或配置文件中的敏感信息
- `config init` 涉及密码输入，需要用户交互

## 初始化

首次使用前运行 `exchange-cli config init` 交互式配置。

也可通过环境变量配置：
- `EXCHANGE_SERVER`
- `EXCHANGE_USERNAME`
- `EXCHANGE_PASSWORD`
- `EXCHANGE_AUTH_TYPE`

## 全局参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--format json\|text` | `json` | 输出格式 |
| `--config <path>` | `~/.exchange-cli/config.json` | 配置文件路径 |
| `--account <email>` | `default_account` | 指定账户 |
| `--verbose` | `false` | 调试模式 |

## 命令速查表

| 命令 | 用途 |
|------|------|
| `config init` | 交互式配置 |
| `config show` | 显示配置 |
| `config test` | 测试连接 |
| `email list` | 查看最近邮件 |
| `email read <id>` | 读取邮件正文 |
| `email send` | 发送邮件 |
| `email reply <id>` | 回复邮件 |
| `email forward <id>` | 转发邮件 |
| `email search <query>` | 搜索邮件 |
| `draft list` | 查看草稿 |
| `draft create` | 创建草稿 |
| `draft send <id>` | 发送草稿 |
| `draft delete <id>` | 删除草稿 |
| `folder list` | 查看文件夹 |
| `folder tree` | 查看目录树 |
| `calendar list` | 查看日历事件 |
| `calendar create` | 创建日历事件 |
| `calendar update <id>` | 更新日历事件 |
| `calendar delete <id>` | 删除日历事件 |
| `task list` | 查看任务 |
| `task create` | 创建任务 |
| `task complete <id>` | 完成任务 |
| `task delete <id>` | 删除任务 |
| `contact list` | 查看联系人 |
| `contact search <query>` | 搜索联系人 |

## JSON 输出格式

成功：`{"ok": true, "data": ..., "count": N}`

错误：`{"ok": false, "error": "...", "code": "ERROR_CODE"}`
