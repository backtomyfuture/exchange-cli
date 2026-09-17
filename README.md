# exchange-cli

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/@backtomyfuture/exchange-cli.svg)](https://www.npmjs.com/package/@backtomyfuture/exchange-cli)
[![Node Version](https://img.shields.io/node/v/@backtomyfuture/exchange-cli.svg)](https://nodejs.org)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)

轻量、面向 AI Agent 与自动化工作流的本地 Microsoft Exchange Server (EWS) 命令行工具。

原生输出结构化 JSON，无缝衔接大语言模型与自动化流水线。纯客户端直连本地部署的 Exchange Server，零外部服务依赖（无需 Docker、数据库或后台常驻守护进程）。

> **适用范围**：专注于**单机运行、单个已授权账号、本地部署的 Exchange Server (On-Premises)**。不适用于 Exchange Online / Microsoft 365（已废弃 Basic/NTLM EWS），亦不提供多租户云端编排能力。

---

## 核心特性

- **Agent-First 原生设计**：默认统一返回结构化 JSON 数据信封（包含 `ok`, `data`, `error`, `code`, `meta.request_id`, `meta.elapsed_ms`），内置 `--dry-run` 预演校验及高危写操作强制 `--confirm` 授权机制。
- **轻量无状态架构**：纯命令行前台进程直连 EWS，无后台常驻 Daemon 守护进程，无运行时数据库依赖，启动迅速且易于容器化与沙箱化调度。
- **全方位协同支持**：
  - **邮件管理**：收发邮件、回复、转发、搜索、更新草稿/元数据、复制/归档/恢复、标记已读/垃圾邮件、正文清洗转换（默认 Markdown，按需提供 HTML）、超长正文截断保护、附件安全下载、EWS/MIME 导入导出、会议邀请应答。
  - **日历与会议**：日程检索、会议创建、更新与取消，细粒度控制参会人邀请通知。
  - **任务待办**：任务列表过滤、状态流转（`NotStarted`, `InProgress`, `Completed` 等）。
  - **联系人与通讯录**：支持查询个人联系人，支持解析企业全局地址簿（GAL / Global Address List）。
  - **文件夹**：浏览层级树，创建、重命名、移动、删除与清空邮件文件夹。
  - **邮箱设置**：自动回复（OOF）、发送前 MailTips、委派读取、服务端收件规则。
- **生产级安全基线**：
  - 本地账号凭证采用 Fernet 对称加密安全存储。
  - 默认强制开启严格的 TLS/SSL 证书校验，原生支持企业私有根证书（CA Bundle）。
  - 流式监听（`email watch`）内置超时时长与事件数量上限约束，彻底杜绝 Agent 子进程挂死死锁。

---

## 快速开始

### 1. 安装

推荐通过 npm 安装跨平台全局包（自动分发适用于当前操作系统的预编译原生二进制）：

```bash
npm install -g @backtomyfuture/exchange-cli
```

### 2. 初始化配置

运行交互式配置向导（输入账号与密码，密码隐藏输入不回显）：

```bash
exchange-cli config init
```

*（注：若企业内网环境提供了预设模板，可通过 `exchange-cli config init --preset <name>` 快速加载模板）*

### 3. 环境与连通性自检

运行健康检查，自动验证本地加密配置、TLS 证书设置以及 EWS 远程连接：

```bash
exchange-cli doctor
```

### 4. 日常操作示例

```bash
# 查看收件箱最新邮件
exchange-cli email list --limit 10

# 读取邮件详情（默认返回轻量化 Markdown 正文）
exchange-cli email read <MESSAGE_ID>

# 发送邮件（写操作需显式确认 --confirm）
exchange-cli email send --to "user@example.com" --subject "工作汇报" --body "请查收附件" --confirm

# 查询企业全局地址簿 (GAL)
exchange-cli contact resolve "张三"
```

---

## 安装方式

### 方式一：npm 全局安装（推荐）

适用于已安装 Node.js (≥ 14，建议 18+) 的 macOS、Linux 与 Windows 环境：

```bash
npm install -g @backtomyfuture/exchange-cli
```

安装后即可在全局 PATH 中调用 `exchange-cli` 命令。

### 方式二：Homebrew Tap (macOS)

macOS 用户可通过独立 Tap 进行安装：

```bash
brew tap backtomyfuture/exchange-cli
brew trust --tap backtomyfuture/exchange-cli
brew install exchange-cli
```

### 方式三：预编译独立二进制 (Standalone)

GitHub Releases 页面针对每个稳定版本均发布了跨平台的独立免安装二进制包：
- **macOS**: `darwin-arm64` (Apple Silicon), `darwin-x64` (Intel)
- **Linux**: `linux-x64`, `linux-arm64`
- **Windows**: `win32-x64`, `win32-ia32`

解压对应平台的归档包后即可直接运行其中的可执行文件，无需依赖 Node 或 Python 环境。

### 方式四：源码安装（Python 开发者）

支持 Python 3.10+ 环境：

```bash
pipx install .
# 或在本地开发环境中
pip install -e ".[dev]"
```

---

## 常用命令一览

| 资源 / 模块 | 主要命令 | 功能说明 |
|------------|---------|----------|
| `config` | `init`, `show` | 账号初始化与配置查看（密码脱敏） |
| `doctor` | `doctor` (`--offline`) | 全链路健康检查与 EWS 连通性诊断 |
| `schema` | `schema` (`<command>`) | 输出机器可读的 CLI 参数与语义契约 |
| `email` | `list`, `read`, `send`, `reply`, `forward`, `search`, `update`, `copy`, `move`, `archive`, `restore`, `mark-read`, `mark-unread`, `mark-junk`, `mark-not-junk`, `delete`, `export`, `import`, `export-mime`, `import-mime`, `respond-meeting`, `watch` | 邮件增删改查、生命周期、导入导出与实时监听 |
| `draft` | `list`, `create`, `update`, `attach`, `detach`, `send`, `delete` | 草稿箱管理、附件编辑与发送 |
| `folder` | `list`, `tree`, `create`, `rename`, `move`, `delete`, `empty` | 邮箱文件夹浏览与生命周期管理 |
| `mailbox` | `oof`, `tips`, `delegates`, `rules` | 自动回复、MailTips、委派读取与收件规则 |
| `calendar` | `list`, `create`, `update`, `delete` | 日程与会议管理 |
| `task` | `list`, `create`, `update`, `complete`, `delete` | 待办任务增删改查 |
| `contact` | `list`, `search`, `resolve` | 个人联系人与企业全局地址簿 (GAL) 查询 |

可通过 `exchange-cli <command> --help` 或 `exchange-cli schema <command>` 动态获取任意子命令的完整选项与参数规范。

---

## AI Agent 集成规范

### 结构化输出协议

所有命令默认输出标准 JSON 格式。

**成功响应（列表示例）：**
```json
{
  "ok": true,
  "count": 2,
  "truncated": false,
  "data": [
    {"id": "AAMk...", "subject": "项目进度同步"},
    {"id": "AAMk...", "subject": "周会纪要"}
  ],
  "meta": {
    "request_id": "94cef4ee-8f9d-...",
    "elapsed_ms": 15.2
  }
}
```

**错误响应示例：**
```json
{
  "ok": false,
  "error": "Connection failed",
  "code": "CONNECTION_ERROR",
  "retryable": true,
  "meta": {
    "request_id": "...",
    "elapsed_ms": 12.3
  }
}
```

### 安全与执行准则

1. **严格授权机制（`--confirm`）**：
   - 产生外部副作用的高影响写操作（如 `email send`、`email reply`、`email forward`、`draft send`、`email import`、`email mark-junk`、`mailbox oof set`、`mailbox rules` 写操作以及各项 `delete`/`empty` 操作），在缺少 `--confirm` 时将直接返回 `CONFIRMATION_REQUIRED` 并拒绝执行。
   - Agent 必须在向用户展示关键影响并获得明确授权后，方可在重试时传入 `--confirm`。
   - 支持 `--dry-run` 选项进行安全预演，不发起实际网络写入，免授权返回操作预检结构。
2. **写操作超时防护**：
   - 当写操作遇到网络波动或超时返回 `WRITE_OUTCOME_UNKNOWN` 时，禁止自动重试，应先通过只读列表或搜索对账。
3. **不可信输入防护**：
   - 邮件主题、正文、附件名和联系人字段均视为不可信数据，不得直接拼入 Shell 命令。长正文建议通过 `--body-file` 文件形式传递。
4. **Token 消耗优化**：
   - `email read` 默认返回清洗后的 Markdown 文本以显著节省上下文 Token。
   - 支持 `--max-body-chars <N>` 针对长邮件实施截断保护。
   - 支持 `--fields id,subject,from,date` 仅投影必要字段。
5. **新到邮件查验（避免服务端索引延迟）**：
   - `email list` 直接读取底层数据库项目录表，新邮件投递落库后毫秒级可见；
   - `email search` 涉及正文检索，受 Exchange 服务端全文搜索异步索引管道（MSExchangeSearch / FAST）约束，新邮件在索引完成前会持续返回 `count: 0`；
   - **因此，判定新邮件是否到达、轮询新邮件或刚发信后的到信对账，必须使用 `email list` 或 `email watch`，严禁依赖 `email search`**。

---

## 环境变量配置

在自动化流水线或沙盒环境中，可通过以下环境变量覆盖配置文件中的对应项：

| 环境变量 | 说明 |
|----------|------|
| `EXCHANGE_SERVER` | Exchange 主机域名（如 `mail.example.com`，切勿使用裸 IP 以避免证书域名不匹配） |
| `EXCHANGE_USERNAME` | 用户名（格式如 `DOMAIN\username` 或 `user@example.com`） |
| `EXCHANGE_PASSWORD` | 账号密码 |
| `EXCHANGE_AUTH_TYPE` | 认证方式：`ntlm`（默认）或 `basic` |
| `EXCHANGE_EMAIL` | 邮箱地址 |
| `EXCHANGE_TIMEOUT_SECONDS` | 请求超时时长（秒，默认 30，范围 1..300） |
| `EXCHANGE_CA_BUNDLE` | 企业私有根证书/证书链路径（亦兼容标准 `REQUESTS_CA_BUNDLE`） |
| `EXCHANGE_NO_VERIFY_SSL` | 设为 `1` 时强制跳过 SSL 校验（不推荐，仅限隔离测试使用） |

---

## 自动化测试

项目包含完备的自动化测试套件与代码静态检查：

```bash
# 运行单元测试
pytest -q

# 静态代码规范检查
ruff check .
```

如需在已配置的真实本地 Exchange 环境下运行只读集成冒烟测试：

```bash
EXCHANGE_LIVE_TEST=1 pytest -m live_exchange -q
```

---

## License

本项目基于 [Apache-2.0](LICENSE) 协议开源。
