#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@backtomyfuture/exchange-cli-darwin-arm64',
  'darwin-x64': '@backtomyfuture/exchange-cli-darwin-x64',
  'linux-x64': '@backtomyfuture/exchange-cli-linux-x64',
  'linux-arm64': '@backtomyfuture/exchange-cli-linux-arm64',
  'win32-x64': '@backtomyfuture/exchange-cli-win32-x64',
  'win32-ia32': '@backtomyfuture/exchange-cli-win32-ia32',
};

const platformKey = `${process.platform}-${process.arch}`;
const ext = process.platform === 'win32' ? '.exe' : '';

function getBinaryPath() {
  if (process.env.EXCHANGE_CLI_BINARY) {
    return process.env.EXCHANGE_CLI_BINARY;
  }

  const pkg = PLATFORM_PACKAGES[platformKey];
  if (!pkg) {
    console.error(`exchange-cli: unsupported platform ${platformKey}`);
    process.exit(1);
  }

  try {
    return require.resolve(`${pkg}/bin/exchange-cli${ext}`);
  } catch {
    const modPath = path.join(
      path.dirname(require.resolve(`${pkg}/package.json`)),
      `bin/exchange-cli${ext}`
    );
    if (fs.existsSync(modPath)) {
      return modPath;
    }
  }

  console.error(`exchange-cli: binary not found for ${platformKey}`);
  console.error('Try: npm install --force @backtomyfuture/exchange-cli');
  process.exit(1);
}

try {
  const binaryPath = getBinaryPath();
  if (process.platform === 'darwin') {
    const { ensureDarwinArm64RuntimeLayout } = require('./runtime-layout');
    ensureDarwinArm64RuntimeLayout(binaryPath);
  }
  execFileSync(binaryPath, process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env },
  });
} catch (e) {
  if (e && e.status != null) {
    process.exit(e.status);
  }
  throw e;
}
