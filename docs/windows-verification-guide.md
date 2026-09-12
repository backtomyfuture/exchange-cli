# Windows 环境安装与验证指南

本文档面向在 Windows 10/11 及 Windows Server 环境下使用 `exchange-cli` 的同事与开发者。

## 1. 安装方式

### 方式 A：npm 全局安装（推荐）

需已安装 Node.js (>= 14)：

```powershell
npm install -g @backtomyfuture/exchange-cli
exchange-cli --version
```

### 方式 B：预编译绿色版二进制

从 GitHub Release 下载 `exchange-cli-windows-x64.zip`，解压后包含 `exchange-cli.exe`。
建议将解压目录加入系统的 `PATH` 环境变量。

### 方式 C：Python pipx / uv 源码安装

需已安装 Python 3.10+：

```powershell
pip install pipx
pipx install .
```

## 2. 账号初始化（企业预设）

公司同事可直接使用预设模式，跳过复杂的服务器与域格式记忆：

```powershell
exchange-cli config init --preset company
```

系统会自动填充：
- **Exchange Server**: `10.72.8.110`（按回车确认）
- **Username**: `hnanet\%USERNAME%`（按回车确认）
- **Auth type**: `ntlm`（按回车确认）
- **Email address**: `%USERNAME%@tianjin-air.com`（按回车确认）
- **Password**: 输入域密码（密码输入时不回显）

## 3. 环境连通性自检

```powershell
exchange-cli doctor
```

自检项说明：
1. `effective_config`: 配置文件解析与私钥读取
2. `tls_verification`: TLS 安全性状态
3. `ews_root`: EWS 远程只读探测，验证域账号认证有效

若自检全部显示 `pass`，说明环境已经就绪。

## 4. 常见问题排查 (Troubleshooting)

- **PowerShell 脚本执行策略拦截**：
  若运行 `npm` 生成的 `.ps1` 脚本提示被系统策略拦截，可在 PowerShell 中运行：
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
- **企业私有 CA 证书**：
  若公司 Exchange 使用内部私有根证书，可指定 CA 路径：
  `$env:REQUESTS_CA_BUNDLE="C:\path\to\corp-ca.crt"`
  或在 `config init` 时传入 `--ca-bundle "C:\path\to\corp-ca.crt"`。
- **用户名格式要求**：
  必须为 `DOMAIN\user`（如 `hnanet\zhangsan`），无需手工输入小写/大写转换，CLI 会自动规范化。
