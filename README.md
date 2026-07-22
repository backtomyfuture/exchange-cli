# exchange-cli

轻量、面向 AI agent 的本地 Microsoft Exchange Server 命令行工具。默认输出 JSON，直接基于 `exchangelib` 和 EWS 工作，不依赖数据库、Docker 或 Web 服务。

项目范围明确限定为：**单机运行、单个 Exchange 账号、本地部署的 Exchange Server**。不面向 Exchange Online / Microsoft 365，也不提供多租户或多账号编排能力。

## 特性

- JSON 优先输出，便于 agent 消费
- 面向单账号本地 Exchange Server
- 覆盖邮件、草稿、文件夹、日历、任务、联系人
- 邮件列表默认直连，实时监听在当前 CLI 前台运行
- 支持配置文件加密存储密码
- 同时规划 `pip` 与 `npm` 分发

## 快速开始

```bash
pip install exchange-cli
exchange-cli config init
exchange-cli email list
```

## 安装

### pip

```bash
pip install exchange-cli
```

### npm

```bash
npm install -g @backtomyfuture/exchange-cli
```

## 常用命令

| 资源 | 子命令 |
|------|--------|
| `config` | `init`, `show`, `test` |
| `email` | `list`, `read`, `send`, `reply`, `forward`, `search` |
| `draft` | `list`, `create`, `send`, `delete` |
| `folder` | `list`, `tree` |
| `calendar` | `list`, `create`, `update`, `delete` |
| `task` | `list`, `create`, `update`, `complete`, `delete` |
| `contact` | `list`, `search` |

## 示例

```bash
exchange-cli email list --limit 10
exchange-cli email read AAMk123
exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello" --confirm
exchange-cli calendar list --start "2024-07-01" --end "2024-07-31"
exchange-cli task create --subject "Review PR" --due "2024-07-20"
exchange-cli contact search "John"
```

## AI Agent 使用说明

默认输出 JSON：

```json
{"ok": true, "count": 2, "data": [...]}
```

错误输出：

```json
{"ok": false, "error": "Connection failed", "code": "CONNECTION_ERROR", "retryable": true}
```

发送邮件、回复、转发，以及永久删除草稿、日历事件或任务时，命令必须带 `--confirm`。带参会人的日历创建也必须带 `--confirm`，因为会向参会人发送邀请。

列表与搜索的 `--limit` 范围为 `1..200`；只接受 `inbox`、`sent`、`drafts`、`trash`、`junk` 五个内置邮件文件夹。附件保存使用排他写入，不覆盖同名文件，也拒绝附件名中的路径穿越。

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

环境变量按字段覆盖配置文件，而不是整体替换配置。`--account` 仅用于断言当前账号，必须与已配置的单账号匹配（忽略大小写），不能切换账号。

`EXCHANGE_NO_VERIFY_SSL=1` 会关闭 TLS 证书校验，只应在已确认风险的受控内网中临时使用，否则可能遭受中间人攻击。Fernet 密钥与密文都保存在同一台机器，只能降低配置文件被单独复制或误读的风险，不能防御同一系统账号已经失陷的情况。

`email list` 和 `email watch` 都在当前 CLI 进程中直接连接本地 Exchange，不启动后台进程。

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

## License

Apache-2.0
