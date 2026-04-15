#!/usr/bin/env node
'use strict';

const fs = require('fs');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@canghe_ai/exchange-cli-darwin-arm64',
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
  if (process.platform !== 'win32') {
    fs.chmodSync(binaryPath, 0o755);
    console.log(`exchange-cli: set executable permission for ${platformKey}`);
  }
} catch {
  console.log(`exchange-cli: platform package ${pkg} not installed`);
  console.log('To fix: npm install --force @canghe_ai/exchange-cli');
}
