# Windows 环境安装与验证指南

本文档介绍如何在 Windows 10/11 及 Windows Server 环境下安装、配置与验证 `exchange-cli`。

---

## 1. 安装方式

### 方式 A：npm 全局安装（推荐）

需已安装 Node.js (>= 14)：

```powershell
npm install -g @backtomyfuture/exchange-cli
exchange-cli --version
```

### 方式 B：预编译独立二进制

从 GitHub Releases 下载 `exchange-cli-windows-x64.zip`（或 32 位版本），解压后包含独立的 `exchange-cli.exe`。
建议将解压后的目录添加至系统的 `PATH` 环境变量中。

### 方式 C：Python pipx / uv 源码安装

需已安装 Python 3.10+：

```powershell
pip install pipx
pipx install .
```

---

## 2. 账号初始化与配置

运行交互式配置向导：

```powershell
exchange-cli config init
```

*若所在企业提供了预设模板，亦可运行 `exchange-cli config init --preset <name>`。*

系统将依次提示以下 4 项核心信息（按回车确认默认值）：
- **Exchange Server**: 填写 Exchange 服务器域名（如 `mail.example.com`）
- **Username**: 填写账号（格式如 `DOMAIN\username` 或 `user@example.com`）
- **Password**: 输入密码（输入时不回显）
- **Email address**: 确认邮箱地址（如 `user@example.com`）

配置完成后将自动执行连接测试并加密保存凭证。

---

## 3. 环境连通性自检

```powershell
exchange-cli doctor
```

自检项说明：
1. `effective_config`: 配置文件解析与本地私钥解密测试
2. `tls_verification`: TLS/SSL 证书有效性与安全性状态
3. `ews_root`: EWS 远程只读探测，验证网络与身份认证有效

若自检各项均显示 `pass`，说明本地环境已就绪。

---

## 4. 常见问题排查 (Troubleshooting)

- **PowerShell 脚本执行策略拦截**：
  若运行 npm 生成的全局 `.ps1` 脚本提示被系统策略拦截，可在 PowerShell 中运行：
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- **企业私有 CA 证书**：
  若企业 Exchange 使用内部私有根证书，可指定 CA 路径：
  ```powershell
  $env:EXCHANGE_CA_BUNDLE="C:\path\to\corp-ca.crt"
  ```
  或在 `config init` 时传入 `--ca-bundle "C:\path\to\corp-ca.crt"`。
- **用户名格式**：
  支持 `DOMAIN\user`（如 `CORP\zhangsan`）或标准邮箱格式，CLI 会自动进行规范化处理。
