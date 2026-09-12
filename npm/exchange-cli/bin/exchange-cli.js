#!/usr/bin/env node

const { spawn } = require('child_process');
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

function renderError(message, code = 'BINARY_NOT_FOUND', exitCode = 1) {
  const isText =
    process.argv.includes('--format=text') ||
    (process.argv.indexOf('--format') !== -1 &&
      process.argv[process.argv.indexOf('--format') + 1] === 'text');
  if (isText) {
    console.error(`Error [${code}]: ${message}`);
  } else {
    console.log(
      JSON.stringify({
        ok: false,
        error: message,
        code: code,
        retryable: false,
      })
    );
  }
  process.exit(exitCode);
}

function getBinaryPath() {
  if (process.env.EXCHANGE_CLI_BINARY) {
    const customBin = process.env.EXCHANGE_CLI_BINARY;
    if (!fs.existsSync(customBin)) {
      renderError(
        `exchange-cli: binary not found at EXCHANGE_CLI_BINARY: ${customBin}`,
        'BINARY_NOT_FOUND',
        1
      );
    }
    return customBin;
  }

  const pkg = PLATFORM_PACKAGES[platformKey];
  if (!pkg) {
    renderError(`exchange-cli: unsupported platform ${platformKey}`, 'PLATFORM_NOT_SUPPORTED', 1);
  }

  try {
    return require.resolve(`${pkg}/bin/exchange-cli${ext}`);
  } catch {
    try {
      const modPath = path.join(
        path.dirname(require.resolve(`${pkg}/package.json`)),
        `bin/exchange-cli${ext}`
      );
      if (fs.existsSync(modPath)) {
        return modPath;
      }
    } catch {
      // Ignore require failure
    }
  }

  renderError(
    `exchange-cli: binary not found for ${platformKey}. Try: npm install --force @backtomyfuture/exchange-cli`,
    'BINARY_NOT_FOUND',
    1
  );
}

try {
  const binaryPath = getBinaryPath();
  if (process.platform === 'darwin') {
    const { ensureDarwinArm64RuntimeLayout } = require('./runtime-layout');
    ensureDarwinArm64RuntimeLayout(binaryPath);
  }

  const child = spawn(binaryPath, process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env },
  });

  child.on('error', (err) => {
    renderError(
      `exchange-cli: failed to spawn binary: ${err.message}`,
      'BINARY_NOT_FOUND',
      1
    );
  });

  const forwardSignal = (signal) => {
    if (child && !child.killed && child.pid) {
      try {
        child.kill(signal);
      } catch {
        // Child already exited
      }
    }
  };

  process.on('SIGINT', () => forwardSignal('SIGINT'));
  process.on('SIGTERM', () => forwardSignal('SIGTERM'));
  process.on('SIGHUP', () => forwardSignal('SIGHUP'));

  child.on('exit', (code, signal) => {
    if (signal) {
      process.removeAllListeners('SIGINT');
      process.removeAllListeners('SIGTERM');
      process.removeAllListeners('SIGHUP');
      try {
        process.kill(process.pid, signal);
      } catch {
        process.exit(128 + 15);
      }
    } else {
      process.exit(code ?? 0);
    }
  });
} catch (e) {
  renderError(`exchange-cli wrapper error: ${e.message || e}`, 'WRAPPER_ERROR', 1);
}
