# `exchange-cli doctor` 调研与评估

日期：2026-08-03
范围：只参考官方文档或官方源码；本文记录调研结论及其后的实现决策。

## 结论

调研结论是：只有当诊断能聚合多个真实故障域、给出稳定的机器可读结果时，才值得新增轻量顶层 `exchange-cli doctor`；它不是“主流 CLI 都有”的必选功能。

后续产品决策为：`doctor` 吸收原 `config test` 的连接探针，`config test` 退役，避免两个诊断入口。当前实现将有效配置、TLS 风险和 EWS 根目录刷新拆成稳定检查项，并在失败时保留错误码和修复建议。

## 官方做法与可提炼的原则

| 官方工具 | 一手资料中的做法 | 对本项目的启示 |
| --- | --- | --- |
| npm | 官方 [`npm doctor`](https://docs.npmjs.com/cli/v11/commands/npm-doctor/) 将检查分为 `connection`、`versions`、`environment`、`permissions`、`cache`，支持仅运行指定组；其 registry 检查会真的发出 ping 请求。当前 [命令总览](https://docs.npmjs.com/cli/commands/) 仍列有该命令。 | 检查必须对应真实依赖与真实故障域；远端检查需要明确其网络行为，并允许后续按组收窄。 |
| Flutter | [Flutter CLI 参考](https://docs.flutter.dev/reference/flutter-cli) 将 `doctor` 定义为已安装工具链的信息入口；[Android 安装文档](https://docs.flutter.dev/platform-integration/android/setup?tab=virtual) 要求用户完成报告的任务后再次运行验证，排障时建议 `flutter doctor -v`。 | 用稳定的分类、状态和下一步建议，而不是只有“失败”；提供受控的详细诊断模式。 |
| Homebrew | [`brew doctor` 手册](https://docs.brew.sh/Manpage#doctor-options) 支持列出及单独运行检查；[Troubleshooting](https://docs.brew.sh/Troubleshooting) 要求阅读每个 warning，同时明确不要未经理解地套用破坏性 Git、所有权或权限变更，并要求提交诊断信息前移除凭据和私有 URL。 | 默认只诊断、不自动修复；输出必须可安全粘贴，绝不泄露密码、密文、key、内部地址或用户名。 |
| GitHub CLI（反例） | 当前 [`gh` 命令总览](https://cli.github.com/manual/gh) 没有顶层 `doctor`，而是提供聚焦的 [`gh auth status`](https://cli.github.com/manual/gh_auth_status)：逐 host 测试认证状态并说明退出码/JSON 行为。 | `doctor` 不是成熟 CLI 的必选项。若只有单一检查，保留领域命令更清晰；若新增，退出码和 JSON 契约要被刻意设计。 |

综合上述官方资料，可采用的最佳实践是：

1. 只检查会阻止实际功能的前置条件，并将每项结果标为 `pass`、`warn`、`fail` 或 `skipped`。
2. 每个非通过项都带稳定 `id`、简短原因和可执行但不自动运行的修复建议。
3. 默认无写操作；不要默认 `--fix`。需要修改配置或权限时，另设明确的写操作。
4. 将远端检查与本地检查分开说明；远端检查应复用真实业务最小路径，而不是只测 TCP 端口。
5. 保持默认 JSON 适合 agent 消费；详细模式可增加诊断上下文，但仍必须脱敏。退出码应与 JSON 的总体健康状态一致。
6. 彼此独立的本地检查应尽量继续执行，以一次输出暴露多个无关联问题；将耗时或会联网的检查做成明确的可选项。

## 当前项目的证据

- [`exchange_cli/core/connection.py`](../../exchange_cli/core/connection.py) 的 `probe_connection()` 创建 EWS `Account` 并执行 `account.root.refresh()`；`config init` 和顶层 [`exchange_cli/commands/doctor.py`](../../exchange_cli/commands/doctor.py) 共用该探针。它比端口探测更有价值，且不读取邮件列表、不产生 Exchange 写操作。
- [`exchange_cli/core/config.py`](../../exchange_cli/core/config.py) 会合并 `EXCHANGE_*` 环境变量与文件配置，并在读取时校验缺失字段、认证类型和超时值；`config show` 仅展示已存储、脱敏后的配置，不能代表最终的有效覆盖结果。
- 同一配置读取路径会将配置目录和配置文件的权限收紧为 `0700` / `0600`。因此不能把现有 `ConfigManager.load_config()` 直接当成严格“只读 doctor”的实现：它会修正权限。新命令若承诺无副作用，应使用只读 `stat`/解析逻辑并报告问题，而不是悄悄 `chmod`。
- [`npm/exchange-cli/bin/exchange-cli.js`](../../npm/exchange-cli/bin/exchange-cli.js) 是 Node 启动器；[`npm/exchange-cli/package.json`](../../npm/exchange-cli/package.json) 要求 Node `>=14`。但若 Node 缺失，npm 启动器本身无法运行到 Python 核心，因此 `doctor` 无法用来诊断该首要启动失败；启动器现有错误信息已应负责提示重新安装或平台包缺失。

需要特别注意，主流工具名称并不自动意味着无副作用：npm 的[当前 `doctor` 源码](https://github.com/npm/cli/blob/latest/lib/commands/doctor.js)在校验缓存时会删除损坏内容并回收无引用内容。因此本项目可借鉴“按组检查”的界面，但不能借鉴这种隐式修复语义。

## 已实施的最小契约

建议命令形态：

```bash
exchange-cli doctor
exchange-cli doctor --offline
```

`doctor` 默认验证有效配置后运行 EWS 根目录刷新；这正是原 `config test` 的最小只读业务探针。`--offline` 跳过远端 EWS 访问，适合只检查本地有效配置与 TLS 设置的场景。由于现有配置读取路径会收紧配置目录和文件权限，`--offline` 的含义是“不连接 EWS”，而不是承诺严格无本地文件副作用。

建议检查项：

| id | 默认 | 预期状态与边界 |
| --- | --- | --- |
| `effective_config` | 是 | 验证配置文件/环境变量合并后是否完整、可解密、认证类型和超时是否合法；不输出账号、用户名、密码或服务器。 |
| `tls_verification` | 是 | `no_verify_ssl=true` 时为 `warn`，提示风险；不能因受控内网场景直接判为连接失败。 |
| `ews_root` | 是（`--offline` 时跳过） | 复用 `probe_connection()` 的 `account.root.refresh()`；失败时保留现有 `AUTH_ERROR`、`CONNECTION_ERROR`、`TIMEOUT_ERROR` 等代码，不抓取邮件或执行写操作。 |

JSON 应有类似如下的稳定骨架：

```json
{
  "ok": true,
  "data": {
    "overall": "warn",
    "checks": [
      {"id": "effective_config", "status": "pass"},
      {"id": "tls_verification", "status": "warn", "remediation": "Enable certificate verification when possible."},
      {"id": "ews_root", "status": "pass"}
    ]
  }
}
```

`fail`（包括默认 EWS 探针失败）返回非零退出码；`warn` 保持零退出码，并由 `overall`/`checks` 供 agent 决策；CLI 用法错误仍维持现有退出码 `2`。这避免直接照搬 `gh auth status --json` 在认证有问题时仍可能返回零的特殊语义。

当检查项将来增多时，可再增加 `--check <id>`（可重复）或 `--list-checks`；不要在 MVP 里先实现大量高噪声的系统扫描。

## 不应照搬的部分

- 不要照搬 npm 的 Git、registry、缓存校验：它们不是 Python/EWS 核心操作的普遍前置条件。Node 仅是 npm 启动器的前置条件，而该启动器缺 Node 时也无法进入 `doctor`。
- 不要将 `doctor` 扩张为“每个邮箱功能都要测试”。根目录刷新是可控的最小 EWS 探针；列邮件、搜索、发信或写入日历会扩大数据访问和副作用。
- 不要自动修复权限/配置，更不要提供默认 `--fix`。默认 `doctor` 会连接 Exchange，因而可能进入服务器审计日志；需要避免远端访问时应明确使用 `--offline`。
- 不要把 `config show` 的脱敏显示当作有效配置诊断，也不要在详细模式输出密码、Fernet key/密文、`EXCHANGE_PASSWORD`、账号或内部 Exchange 主机信息。

## 决策建议

已按“一个命令产出可交给支持人员的分项健康报告”的目标实施顶层 `doctor`，并移除 `config test`。文档统一推荐 `doctor`；只需本地检查时使用 `doctor --offline`。
