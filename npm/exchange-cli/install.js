#!/usr/bin/env node
'use strict';

const fs = require('fs');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@backtomyfuture/exchange-cli-darwin-arm64',
  'darwin-x64': '@backtomyfuture/exchange-cli-darwin-x64',
  'linux-x64': '@backtomyfuture/exchange-cli-linux-x64',
  'linux-arm64': '@backtomyfuture/exchange-cli-linux-arm64',
  'win32-x64': '@backtomyfuture/exchange-cli-win32-x64',
  'win32-ia32': '@backtomyfuture/exchange-cli-win32-ia32',
};

const platformKey = `${process.platform}-${process.arch}`;
const pkg = PLATFORM_PACKAGES[platformKey];

if (!pkg) {
  console.log(`exchange-cli: no binary for ${platformKey}, skipping`);
  process.exit(0);
}

const ext = process.platform === 'win32' ? '.exe' : '';

try {
  const binaryPath = require.resolve(`${pkg}/bin/exchange-cli${ext}`);
  if (process.platform === 'darwin') {
    const { ensureDarwinArm64RuntimeLayout } = require('./bin/runtime-layout');
    ensureDarwinArm64RuntimeLayout(binaryPath, (message) => console.log(message));
  }
  if (process.platform !== 'win32') {
    fs.chmodSync(binaryPath, 0o755);
    console.log(`exchange-cli: set executable permission for ${platformKey}`);
  }
} catch {
  console.log(`exchange-cli: platform package ${pkg} not installed`);
  console.log('To fix: npm install --force @backtomyfuture/exchange-cli');
}
