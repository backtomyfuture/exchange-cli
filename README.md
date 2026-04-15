# exchange-cli

轻量、面向 AI agent 的 Microsoft Exchange Web Services 命令行工具。默认输出 JSON，直接基于 `exchangelib` 工作，不依赖数据库、Docker 或 Web 服务。

## 特性

- JSON 优先输出，便于 agent 消费
- 覆盖邮件、草稿、文件夹、日历、任务、联系人
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
npm install -g @canghe_ai/exchange-cli
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
exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello"
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
{"ok": false, "error": "Connection failed", "code": "CONNECTION_ERROR"}
```

可使用以下环境变量覆盖配置文件：

- `EXCHANGE_SERVER`
- `EXCHANGE_USERNAME`
- `EXCHANGE_PASSWORD`
- `EXCHANGE_AUTH_TYPE`

## License

Apache-2.0
