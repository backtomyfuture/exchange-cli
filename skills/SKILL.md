---
name: exchange-cli
version: 1.3.0
description: |
  Exchange/Outlook 邮件与办公 CLI 工具：收发邮件、搜索邮件、管理草稿、查看和创建日历事件、管理任务待办、查询联系人、实时监听新邮件。
  通过 exchange-cli 直连 Exchange/Office 365 服务器，输出结构化 JSON，专为 AI agent 设计。
  当用户需要操作 Exchange 或 Outlook 邮箱时务必使用——包括但不限于：查看收件箱、发邮件给某人、
  回复或转发邮件、搜索特定邮件、创建或查看日历会议、管理任务待办、查找联系人、实时监听新邮件到达。
  即使用户只是说"帮我查一下邮件"、"发一封邮件给xxx"、"看看今天有什么会议"、"帮我建个会议"、
  "把这个任务标记为完成"、"找一下张三的邮箱"、"有新邮件来了通知我"，也应该触发。
  不适用于：Gmail、飞书邮箱、其他非 Exchange 的邮件系统。
metadata:
  requires:
    bins: ["exchange-cli"]
  cliHelp: "exchange-cli --help"
---

# exchange-cli

exchange-cli 是一个面向 AI agent 的 Microsoft Exchange Web Services CLI 工具。直连 Exchange/Office 365，不依赖数据库、Docker 或 Web 服务。所有命令默认输出 JSON。

## 安全与执行规则

- **发送邮件前**必须向用户确认收件人、主题和正文摘要
- **删除操作**（邮件、日历事件、任务、草稿）执行前必须确认
- 不要在聊天中暴露密码或 `.key` 文件内容
- `config init` 需要用户交互输入密码，不能自动化跳过

## 初始化检查

首次使用前运行 `exchange-cli config test` 验证连接。如果返回 `CONFIG_NOT_FOUND` 错误码，需要引导用户运行 `exchange-cli config init` 交互式配置。

也可通过环境变量配置（适合 CI 或自动化场景）：

| 环境变量 | 说明 |
|----------|------|
| `EXCHANGE_SERVER` | Exchange 服务器地址 |
| `EXCHANGE_USERNAME` | 用户名（如 `DOMAIN\user`） |
| `EXCHANGE_PASSWORD` | 密码（明文） |
| `EXCHANGE_AUTH_TYPE` | 认证类型：`ntlm`（默认）或 `basic` |
| `EXCHANGE_EMAIL` | 邮箱地址 |
| `EXCHANGE_NO_VERIFY_SSL` | 设为 `1` 跳过 SSL 验证 |
| `EXCHANGE_DOMAIN` | 域名（用于自动推导用户名） |
| `EXCHANGE_EMAIL_SUFFIX` | 邮箱后缀（用于自动推导邮箱地址） |
| `EXCHANGE_CLI_DISABLE_DAEMON` | 设为 `1` 禁用后台 daemon（强制直连模式） |

环境变量优先级高于配置文件。

## 全局参数

所有命令均支持以下全局参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--format json\|text` | `json` | 输出格式 |
| `--config <path>` | `~/.exchange-cli` | 配置目录路径（也可通过 `EXCHANGE_CLI_CONFIG` 环境变量设置） |
| `--account <email>` | 配置文件中的 `default_account` | 指定使用哪个账户 |
| `--verbose` | `false` | 调试信息输出到 stderr |

## JSON 输出格式

**成功（单条数据）：**
```json
{"ok": true, "data": {"id": "AAMk...", "subject": "..."}}
```

**成功（列表数据）：**
```json
{"ok": true, "count": 5, "data": [{...}, {...}]}
```

**错误：**
```json
{"ok": false, "error": "Connection failed", "code": "CONNECTION_ERROR"}
```

**错误码一览：**

| 错误码 | 含义 | 处理建议 |
|--------|------|---------|
| `CONFIG_NOT_FOUND` | 未找到配置 | 引导运行 `config init` |
| `AUTH_ERROR` | 认证失败 | 检查用户名密码 |
| `CONNECTION_ERROR` | 连接失败 | 检查服务器地址和网络 |
| `NOT_FOUND` | 资源不存在 | ID 可能无效或已删除 |
| `INVALID_INPUT` | 参数错误 | 检查必填参数和格式 |
| `SERVER_ERROR` | 服务端错误 | 重试或检查 Exchange 服务状态 |
| `DAEMON_START_FAILED` | daemon 启动失败 | 检查配置或设置 `EXCHANGE_CLI_DISABLE_DAEMON=1` |
| `DAEMON_UNAVAILABLE` | daemon 无法连接 | 运行 `daemon start` 或设置 `EXCHANGE_CLI_DISABLE_DAEMON=1` |
| `WATCH_SUBSCRIBE_FAILED` | watch 订阅失败 | 检查文件夹名称和账户权限 |
| `WATCH_STREAM_ERROR` | 事件流中断 | 重新运行 `email watch` |

---

## 命令参考

### config — 配置管理

#### config init
交互式配置，需要用户输入。

```bash
exchange-cli config init
```

#### config show
显示当前配置（密码已脱敏）。

```bash
exchange-cli config show
```

返回数据：
```json
{
  "ok": true,
  "data": {
    "version": 1,
    "default_account": "user@example.com",
    "accounts": {
      "user@example.com": {
        "server": "mail.example.com",
        "username": "DOMAIN\\user",
        "password": "********",
        "auth_type": "ntlm"
      }
    }
  }
}
```

#### config test
测试 Exchange 连接。

```bash
exchange-cli config test
exchange-cli config test --account other@example.com
```

---

### email — 邮件操作

#### email list

```bash
exchange-cli email list                                # 收件箱最近 20 封
exchange-cli email list --folder sent --limit 50       # 已发送最近 50 封
exchange-cli email list --unread                       # 仅未读邮件
exchange-cli email list --folder drafts --limit 10
exchange-cli email list --unread --with-preview        # 含正文预览（较慢）
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--folder` | `inbox` | 文件夹：`inbox`, `sent`, `drafts`, `trash`, `junk` |
| `--limit` | `20` | 返回数量 |
| `--unread` | `false` | 仅返回未读 |
| `--with-preview` | `false` | 在摘要中附带正文预览（数量大时较慢） |

> `email list` 默认通过本地 daemon 加速查询。若 daemon 未运行会自动启动；若需禁用，设 `EXCHANGE_CLI_DISABLE_DAEMON=1`。

返回数据中每条邮件的字段：

```json
{
  "id": "AAMkAD...",
  "subject": "Quarterly Report",
  "sender": {"name": "Boss", "email": "boss@x.com"},
  "to": [{"name": "John", "email": "john@x.com"}],
  "cc": [],
  "datetime_received": "2024-07-15T10:30:00+08:00",
  "datetime_sent": "2024-07-15T10:29:55+08:00",
  "is_read": true,
  "has_attachments": true,
  "importance": "Normal",
  "body_preview": "Please find the quarterly..."
}
```

#### email read

```bash
exchange-cli email read MESSAGE_ID                          # 默认 markdown 格式（LLM 友好）
exchange-cli email read MESSAGE_ID --body-format html       # 原始 HTML
exchange-cli email read MESSAGE_ID --save-attachments ./downloads
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MESSAGE_ID`（必填） | — | 邮件 ID（从 `email list` 获取） |
| `--body-format` | `markdown` | 正文输出格式：`markdown`（默认，自动清洗 HTML 为 Markdown）或 `html`（原始 HTML） |
| `--save-attachments <dir>` | — | 将附件保存到指定目录 |

返回的详细邮件还额外包含 `body`（正文，格式由 `--body-format` 控制）、`body_format`（当前格式）、`bcc`、`attachments` 数组。

#### email send

```bash
exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello"
exchange-cli email send --to "a@x.com" --to "b@x.com" --cc "c@x.com" --subject "Hi" --body "Hello"
exchange-cli email send --to "a@x.com" --subject "Report" --body-file ./content.html --body-type html
exchange-cli email send --to "a@x.com" --subject "Report" --body "See attached" --attach report.pdf --attach data.xlsx
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 收件人（可多次使用） |
| `--cc` | 否 | 抄送（可多次使用） |
| `--bcc` | 否 | 密送（可多次使用） |
| `--subject` | 是 | 主题 |
| `--body` | 二选一 | 正文内容 |
| `--body-file` | 二选一 | 从文件读取正文 |
| `--body-type` | 否 | `text`（默认）或 `html` |
| `--attach` | 否 | 附件路径（可多次使用） |

#### email reply

```bash
exchange-cli email reply MESSAGE_ID --body "Thanks"
exchange-cli email reply MESSAGE_ID --body "Thanks everyone" --all
```

| 参数 | 说明 |
|------|------|
| `MESSAGE_ID`（必填） | 要回复的邮件 ID |
| `--body`（必填） | 回复内容 |
| `--all` | 回复全部收件人 |

#### email forward

```bash
exchange-cli email forward MESSAGE_ID --to "b@x.com"
exchange-cli email forward MESSAGE_ID --to "b@x.com" --to "c@x.com" --body "FYI"
```

| 参数 | 说明 |
|------|------|
| `MESSAGE_ID`（必填） | 要转发的邮件 ID |
| `--to`（必填） | 转发目标（可多次使用） |
| `--body` | 附加说明文字 |

#### email search

```bash
exchange-cli email search "quarterly report"
exchange-cli email search "keyword" --folder sent --limit 50
exchange-cli email search "project" --start "2024-01-01" --end "2024-06-30"
exchange-cli email search "meeting" --with-preview
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `QUERY`（必填） | — | 搜索关键词（匹配主题和正文） |
| `--folder` | `inbox` | 搜索的文件夹 |
| `--limit` | `20` | 最大结果数 |
| `--start` | — | 起始日期 `YYYY-MM-DD` |
| `--end` | — | 结束日期 `YYYY-MM-DD` |
| `--with-preview` | `false` | 结果中附带正文预览 |

#### email watch
实时监听文件夹新邮件，每条事件以独立 JSON 行输出到 stdout（NDJSON 流）。内部使用 Exchange 流式订阅 + daemon 后台进程，断线后自动回填补齐。按 Ctrl+C 停止。

```bash
exchange-cli email watch                              # 监听收件箱
exchange-cli email watch --folder inbox --backfill-minutes 5
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--folder` | `inbox` | 监听的文件夹 |
| `--backfill-minutes` | `10` | 流式重连后回填的时间窗口（分钟） |

事件输出格式（每行一个 JSON 对象）：

```json
{"ok": true, "data": {"event_type": "new_mail", "timestamp": "2024-07-15T10:30:00Z", "folder": "inbox", "account": "user@x.com", "message": {"id": "AAMk...", "subject": "Hello", "sender": {...}, "is_read": false}}}
{"ok": true, "data": {"event_type": "heartbeat", "timestamp": "2024-07-15T10:30:15Z"}}
{"ok": true, "data": {"event_type": "watcher_status", "status": "streaming_connected", "folder": "inbox"}}
```

主要事件类型：

| `event_type` | 说明 |
|--------------|------|
| `new_mail` / `created` | 新邮件到达，包含 `message` 摘要 |
| `modified` | 邮件被修改（如已读状态变化） |
| `deleted` | 邮件被删除 |
| `backfill_new_mail` | 重连后回填的近期邮件 |
| `watcher_status` | 监听器状态变化（连接/断开/错误） |
| `heartbeat` | 心跳保活（每 15 秒一次） |

---

### draft — 草稿管理

#### draft list

```bash
exchange-cli draft list
exchange-cli draft list --limit 50
```

#### draft create

```bash
exchange-cli draft create --to "a@x.com" --subject "Draft Title" --body "Draft content"
exchange-cli draft create --subject "Internal" --body "<h1>Title</h1>" --body-type html
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 否 | 收件人（可多次使用） |
| `--cc` | 否 | 抄送（可多次使用） |
| `--subject` | 是 | 主题 |
| `--body` | 是 | 正文 |
| `--body-type` | 否 | `text`（默认）或 `html` |

#### draft send

```bash
exchange-cli draft send DRAFT_ID
```

#### draft delete

```bash
exchange-cli draft delete DRAFT_ID
```

---

### folder — 文件夹浏览

#### folder list
列出顶层文件夹。

```bash
exchange-cli folder list
```

返回数据：
```json
{
  "id": "AAMk...",
  "name": "Inbox",
  "total_count": 150,
  "unread_count": 5,
  "child_folder_count": 2
}
```

#### folder tree
递归显示所有文件夹，每个节点带 `depth` 字段表示层级。

```bash
exchange-cli folder tree
```

---

### calendar — 日历事件

#### calendar list

```bash
exchange-cli calendar list                                          # 今天的事件
exchange-cli calendar list --start "2024-07-01" --end "2024-07-31"  # 指定日期范围
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start` | 今天 00:00 | 起始时间 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM` |
| `--end` | 明天 00:00 | 结束时间 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM` |

返回数据：
```json
{
  "id": "AAMk...",
  "subject": "Weekly Sync",
  "start": "2024-07-15T10:00:00+08:00",
  "end": "2024-07-15T11:00:00+08:00",
  "location": "Room A",
  "organizer": {"name": "Boss", "email": "boss@x.com"},
  "attendees": [{"name": "John", "email": "john@x.com", "response": "Accept"}],
  "is_all_day": false,
  "body_preview": "Agenda: ..."
}
```

#### calendar create

```bash
exchange-cli calendar create --subject "Meeting" --start "2024-07-15 10:00" --end "2024-07-15 11:00"
exchange-cli calendar create --subject "Sync" --start "2024-07-15 14:00" --end "2024-07-15 14:30" \
  --attendees "a@x.com,b@x.com" --location "Room A" --body "Discussion items"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--subject` | 是 | 事件标题 |
| `--start` | 是 | 开始时间 `YYYY-MM-DD HH:MM` |
| `--end` | 是 | 结束时间 `YYYY-MM-DD HH:MM` |
| `--location` | 否 | 地点 |
| `--body` | 否 | 事件描述 |
| `--attendees` | 否 | 参会人邮箱（逗号分隔，添加后自动发送会议邀请） |

#### calendar update

```bash
exchange-cli calendar update EVENT_ID --subject "New Title"
exchange-cli calendar update EVENT_ID --start "2024-07-16 10:00" --end "2024-07-16 11:00"
```

| 参数 | 说明 |
|------|------|
| `EVENT_ID`（必填） | 事件 ID |
| `--subject` | 新标题 |
| `--start` | 新开始时间 |
| `--end` | 新结束时间 |
| `--location` | 新地点 |

#### calendar delete

```bash
exchange-cli calendar delete EVENT_ID
```

---

### task — 任务管理

#### task list

```bash
exchange-cli task list
exchange-cli task list --limit 100
exchange-cli task list --status NotStarted
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | `50` | 最大数量 |
| `--status` | — | 按状态筛选：`NotStarted`, `InProgress`, `Completed`, `WaitingOnOthers`, `Deferred` |

返回数据：
```json
{
  "id": "AAMk...",
  "subject": "Review PR",
  "status": "NotStarted",
  "due_date": "2024-07-20",
  "start_date": null,
  "complete_date": null,
  "percent_complete": 0,
  "importance": "Normal",
  "body_preview": ""
}
```

#### task create

```bash
exchange-cli task create --subject "Review PR"
exchange-cli task create --subject "Write report" --due "2024-07-20" --body "Q2 report" --status InProgress
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--subject` | 是 | 任务标题 |
| `--due` | 否 | 截止日期 `YYYY-MM-DD` |
| `--body` | 否 | 任务描述 |
| `--status` | 否 | 初始状态（默认 `NotStarted`） |

#### task update

```bash
exchange-cli task update TASK_ID --subject "Updated title"
exchange-cli task update TASK_ID --due "2024-08-01" --status InProgress
```

#### task complete

```bash
exchange-cli task complete TASK_ID
```

将任务标记为 `Completed`，`percent_complete` 设为 100。

#### task delete

```bash
exchange-cli task delete TASK_ID
```

---

### contact — 联系人

#### contact list

```bash
exchange-cli contact list
exchange-cli contact list --limit 100
```

返回数据：
```json
{
  "id": "AAMk...",
  "display_name": "John Doe",
  "given_name": "John",
  "surname": "Doe",
  "emails": [{"email": "john@x.com", "label": "EmailAddress1"}],
  "phones": [{"number": "+1234567890", "label": "BusinessPhone"}],
  "company": "Acme Corp",
  "department": "Engineering",
  "job_title": "Engineer"
}
```

#### contact search

```bash
exchange-cli contact search "John"
exchange-cli contact search "engineering" --limit 50
```

| 参数 | 说明 |
|------|------|
| `QUERY`（必填） | 搜索关键词（匹配姓名和邮箱） |
| `--limit` | 最大结果数（默认 20） |

---

### daemon — 后台守护进程

daemon 是 `email list` 快速查询和 `email watch` 实时监听的基础组件，通过 Unix Socket 与 CLI 通信，首次使用时会自动启动。通常无需手动管理，仅在调试或需要明确控制时使用。

#### daemon start

```bash
exchange-cli daemon start                        # 启动 daemon（已运行则无操作）
exchange-cli daemon start --wait-seconds 60      # 延长启动超时
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--wait-seconds` | `30` | 等待 daemon 启动的超时时间（秒） |

返回数据：
```json
{"ok": true, "data": {"status": "running", "pid": 12345, "socket": "/Users/user/.exchange-cli/run/agent.sock", "started": true}}
```

#### daemon status

```bash
exchange-cli daemon status
```

返回 `{"status": "running", "pid": ..., "started_at": "..."}` 或 `{"status": "stopped"}`。

#### daemon stop

```bash
exchange-cli daemon stop
```

优雅停止 daemon 进程，返回 `{"status": "stopped", "changed": true/false}`。

> **注意**：daemon 日志写入 `~/.exchange-cli/run/agent.log`，可在此排查启动问题。

---

## 常见工作流

### 查看并回复邮件

```bash
exchange-cli email list --unread --limit 5
exchange-cli email read MESSAGE_ID                  # 默认输出 markdown 格式正文
exchange-cli email reply MESSAGE_ID --body "收到，谢谢！"
```

### 发送带附件的邮件

```bash
exchange-cli email send --to "boss@x.com" --subject "Q2 Report" \
  --body "Hi, please find the report attached." \
  --attach ./report.pdf --attach ./data.xlsx
```

### 查找某人的邮件地址然后发邮件

```bash
exchange-cli contact search "张三"
# 从结果中获取邮箱地址
exchange-cli email send --to "zhangsan@company.com" --subject "Hi" --body "..."
```

### 查看今天日程并创建新会议

```bash
exchange-cli calendar list
exchange-cli calendar create --subject "Team Sync" \
  --start "2024-07-15 14:00" --end "2024-07-15 14:30" \
  --attendees "alice@x.com,bob@x.com" --location "Meeting Room 3"
```

### 先存草稿确认后再发送

```bash
exchange-cli draft create --to "client@x.com" --subject "Proposal" --body "..."
# 确认内容后
exchange-cli draft send DRAFT_ID
```

### 搜索特定时间段的邮件

```bash
exchange-cli email search "项目进度" --start "2024-06-01" --end "2024-06-30" --folder inbox
```

### 实时监听新邮件并处理

```bash
# 启动监听（会阻塞，每条新邮件输出一行 JSON）
exchange-cli email watch --folder inbox

# 典型 agent 用法：管道接收并逐行处理
exchange-cli email watch | while IFS= read -r line; do
  echo "$line" | jq '.data | select(.event_type == "new_mail") | .message'
done
```

### 检查 daemon 状态

```bash
exchange-cli daemon status   # 查看是否运行中
exchange-cli daemon start    # 手动启动
exchange-cli daemon stop     # 停止
```
