# exchange-cli

轻量、面向 AI agent 的本地 Microsoft Exchange Server 命令行工具。默认输出 JSON，直接基于 `exchangelib` 和 EWS 工作，不依赖数据库、Docker 或 Web 服务。

项目范围明确限定为：**单机运行、单个 Exchange 账号、本地部署的 Exchange Server**。不面向 Exchange Online / Microsoft 365，也不提供多租户或多账号编排能力。

## 特性

- JSON 优先输出，便于 agent 消费
- 面向单账号本地 Exchange Server
- 覆盖邮件、草稿、文件夹、日历、任务、联系人
- 邮件列表默认直连，实时监听在当前 CLI 前台运行
- 支持配置文件加密存储密码
- 当前正式分发入口是 npm 平台二进制；Python 源码安装适用于开发者

## 快速开始

已有 Node 的同事优先使用已发布的 npm 包：

```bash
npm install -g @backtomyfuture/exchange-cli
# 普通初始化；公司同事可使用预设一键填入服务器与域（仅需输密码）：
exchange-cli config init --preset company
exchange-cli doctor
exchange-cli email list
```

没有 Node、但有 Python 3.10+ 的开发者可以从源码安装：

```bash
pipx install .
# 或: uv tool install .
exchange-cli config init
```

当前 PyPI 没有 `exchange-cli` 包，不要使用 `pip install exchange-cli`。

## 安装

### npm（推荐）

```bash
npm install -g @backtomyfuture/exchange-cli
```

安装后会拉取当前平台的二进制包。首次启动在 macOS 上可能需要十几秒。

### Homebrew（macOS 同事）

这个工具面向公司内网 Exchange，不适合进 Homebrew 官方 core。同事可以装自己的 tap：

```bash
brew tap backtomyfuture/exchange-cli
brew trust --tap backtomyfuture/exchange-cli
brew install exchange-cli
exchange-cli --version
```

Homebrew 6 会拒绝未信任的第三方 formula。第一次安装需要 `brew trust`；这不是 Homebrew 官方 core。公式从 GitHub Release 下载当前平台的预编译二进制。

### 从源码安装（开发者）

```bash
pipx install .
# 或: pip install -e ".[dev]"
```

发布 Python 包前，wheel 只包含 `exchange_cli*`，不打包 `tests`、`docs`、`npm` 或工作区目录。

### 独立二进制

CI 为 darwin/linux/windows 的 arm64 与 x64 构建平台包。没有 Node 的同事可以解压对应平台目录中的 `bin/exchange-cli` 直接运行。

## 常用命令

| 资源 | 子命令 |
|------|--------|
| `config` | `init`, `show` |
| 诊断 | `doctor`（`--offline` 跳过 EWS 连接探针） |
| `schema` | 机器可读命令契约 |
| `email` | `list`, `read`, `send`, `reply`, `forward`, `search`, `mark-read`, `mark-unread`, `move`, `delete`, `watch` |
| `draft` | `list`, `create`, `send`, `delete` |
| `folder` | `list`, `tree` |
| `calendar` | `list`, `create`, `update`, `delete` |
| `task` | `list`, `create`, `update`, `complete`, `delete` |
| `contact` | `list`, `search`, `resolve` |

## 示例

```bash
exchange-cli doctor
exchange-cli doctor --offline
exchange-cli schema email.send
exchange-cli email list --limit 10
exchange-cli email read AAMk123 --fields id,subject,body
exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello" --confirm
exchange-cli contact resolve "张三"
exchange-cli calendar list --start "2024-07-01" --end "2024-07-31"
exchange-cli task create --subject "Review PR" --due "2024-07-20"
exchange-cli contact search "John"
```

## AI Agent 使用说明

默认输出 JSON：

```json
{"ok": true, "count": 2, "truncated": false, "data": [...]}
```

错误输出：

```json
{"ok": false, "error": "Connection failed", "code": "CONNECTION_ERROR", "retryable": true}
```

写操作在超时、连接中断或服务器繁忙时返回：

```json
{"ok": false, "error": "...", "code": "WRITE_OUTCOME_UNKNOWN", "retryable": false, "outcome": "unknown"}
```

这时不要自动重试，先用 `email list`、`calendar list` 或 `task list` 对账。

发送邮件、回复、转发，以及永久删除邮件、草稿、日历事件或任务时，命令必须带 `--confirm`。带参会人且会发邀请的日历创建，以及 `--notify all` 的会议更新，也必须带 `--confirm`。

列表与搜索的 `--limit` 范围为 `1..200`。`--folder` 接受 `inbox`、`sent`、`drafts`、`trash`、`junk`，也可以是文件夹路径或文件夹 ID。`email delete` 默认移入回收站；只有 `--permanent` 才会永久删除。附件保存使用排他写入，不覆盖同名文件，也拒绝附件名中的路径穿越。

`email read --fields id,subject,body` 可以省略原始 HTML。`contact resolve` 查询公司通讯录，不是个人联系人文件夹。

`task list --status` 在客户端筛选，因为 EWS 不能按 `status` 字段过滤。结果可能带 `truncated: true`，表示扫描上限内还有未返回的匹配项。

日历 `--notify none|all` 控制是否通知参会人。默认创建无参会人日程不发邀请；有参会人时默认 `all`。更新和删除默认 `none`，避免把“自己日历改成功”当成“会议已通知所有人”。

可使用以下环境变量覆盖配置文件：

- `EXCHANGE_SERVER`
- `EXCHANGE_USERNAME`
- `EXCHANGE_PASSWORD`
- `EXCHANGE_AUTH_TYPE`
- `EXCHANGE_NO_VERIFY_SSL`
- `EXCHANGE_DOMAIN`
- `EXCHANGE_EMAIL_SUFFIX`
- `EXCHANGE_EMAIL`
- `EXCHANGE_TIMEOUT_SECONDS`（默认 `30`，范围 `1..300`）
- `EXCHANGE_CA_BUNDLE`（或标准的 `REQUESTS_CA_BUNDLE`，企业私有 CA 根证书/证书链路径）

环境变量按字段覆盖配置文件，而不是整体替换配置。`--account` 仅用于断言当前账号，必须与已配置的单账号匹配（忽略大小写），不能切换账号。

`EXCHANGE_SERVER` 应是主机域名（如 `mail.example.com`），不要配置成裸 IP。若配置为 IP 地址，会因为服务端证书未将该 IP 写入保护列表（No IP SAN）而引发 TLS 主机名不匹配错误（IP mismatch）。

`exchange-cli doctor` 会检查有效配置、TLS 证书校验设置与 CA 路径，并通过刷新 EWS 根目录验证认证和最小只读访问；它不会读取邮件或写入 Exchange。加 `--offline` 时仅跳过这项 EWS 远端探针。如果关闭了 TLS 校验（`no_verify_ssl=true`）或 CA 路径无效，`doctor` 会判定为 `fail` 并返回非零退出码，阻止带安全隐患的配置在企业内扩散。

企业私有 CA 证书环境应配置企业 CA 路径（通过 `EXCHANGE_CA_BUNDLE`、`REQUESTS_CA_BUNDLE` 或配置文件的 `ca_bundle` 字段），而不是把关闭校验当成默认模板。`EXCHANGE_NO_VERIFY_SSL=1` 会彻底关闭 TLS 证书校验，仅限已确认风险的隔离沙盒排障使用。Fernet 密钥与密文都保存在同一台机器，只能降低配置文件被单独复制或误读的风险，不能防御同一系统账号已经失陷的情况。

`email list` 和 `email watch` 都在当前 CLI 进程中直接连接本地 Exchange，不启动后台进程。`email watch` 的新邮件事件只包含 item id；需要正文时再调用 `email read`。可用 `--duration` 和 `--max-events` 限制运行时间。认证失败会停止监听，不会无限重连。

调用时使用参数数组，不要把不可信邮件内容拼进 shell。检查退出码；非零即失败。限制运行时间，尤其是 `email watch`。

Skill 位于 `skills/SKILL.md`，已随 npm 包一并分发（安装后位于 package 的 `skills/` 目录），也可直接从仓库复制到 agent 的 skills 目录。

默认测试不访问真实邮箱。需要在已配置的本地 Exchange 上做只读冒烟时，显式运行：

```bash
EXCHANGE_LIVE_TEST=1 pytest -m live_exchange -q
```

该测试只验证连接、根目录刷新和最多一封 Inbox 摘要，不发送、修改或删除任何项目。

## Release Checklist

- 在 `exchange_cli/__init__.py` 更新唯一 Python 版本源
- 运行 `python scripts/check_release_versions.py`，确认 Python 与全部 npm 包版本一致
- 重新编译平台二进制到 `npm/platforms/darwin-arm64/bin/exchange-cli`
- 本地验证：`exchange-cli --version`、`pytest -q`、`ruff check .`
- 六个平台全部构建、执行 `--version` 冒烟并完成 `npm pack` 后，才进入唯一发布任务
- 唯一发布任务顺序发布六个平台包，最后发布主包；npm 不支持事务，失败时仍需人工核对 registry
- 发布后验证：`npm view @backtomyfuture/exchange-cli version` 与 `npm i -g @backtomyfuture/exchange-cli@<version>`
- 比较实际二进制 `--version`，不要只检查包元数据

## License

Apache-2.0
