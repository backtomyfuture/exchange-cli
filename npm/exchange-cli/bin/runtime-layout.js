#!/usr/bin/env node

'use strict';

const fs = require('fs');
const path = require('path');

function copyFileWithMode(src, dst) {
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
  try {
    const stat = fs.statSync(src);
    fs.chmodSync(dst, stat.mode & 0o777);
  } catch {
    // Best effort only.
  }
}

function copyDirRecursive(srcDir, dstDir) {
  fs.mkdirSync(dstDir, { recursive: true });
  const entries = fs.readdirSync(srcDir, { withFileTypes: true });
  for (const entry of entries) {
    const src = path.join(srcDir, entry.name);
    const dst = path.join(dstDir, entry.name);
    if (entry.isDirectory()) {
      copyDirRecursive(src, dst);
      continue;
    }
    copyFileWithMode(src, dst);
  }
}

function copyIfMissing(src, dst, logger) {
  if (fs.existsSync(dst) || !fs.existsSync(src)) {
    return false;
  }
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    copyDirRecursive(src, dst);
  } else {
    copyFileWithMode(src, dst);
  }
  if (logger) {
    logger(`exchange-cli: repaired missing runtime path ${path.basename(dst)}`);
  }
  return true;
}

function resolveFrameworkVersionDir(internalDir) {
  const versionsDir = path.join(internalDir, 'Python.framework', 'Versions');
  if (!fs.existsSync(versionsDir)) {
    return null;
  }
  const currentDir = path.join(versionsDir, 'Current');
  if (fs.existsSync(path.join(currentDir, 'Python'))) {
    return currentDir;
  }

  const candidates = fs
    .readdirSync(versionsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== 'Current')
    .map((entry) => path.join(versionsDir, entry.name))
    .filter((dirPath) => fs.existsSync(path.join(dirPath, 'Python')))
    .sort();

  if (candidates.length === 0) {
    return null;
  }
  return candidates[candidates.length - 1];
}

function ensureDarwinArm64RuntimeLayout(binaryPath, logger = null) {
  if (!(process.platform === 'darwin' && process.arch === 'arm64')) {
    return { changed: false };
  }
  const binDir = path.dirname(binaryPath);
  const internalDir = path.join(binDir, '_internal');
  if (!fs.existsSync(internalDir)) {
    return { changed: false };
  }

  const frameworkVersionDir = resolveFrameworkVersionDir(internalDir);
  if (!frameworkVersionDir) {
    return { changed: false };
  }
  const sourcePython = path.join(frameworkVersionDir, 'Python');
  const sourceResources = path.join(frameworkVersionDir, 'Resources');

  const targets = [
    { src: sourcePython, dst: path.join(internalDir, 'Python') },
    { src: sourcePython, dst: path.join(internalDir, 'Python.framework', 'Python') },
    { src: sourceResources, dst: path.join(internalDir, 'Python.framework', 'Resources') },
    {
      src: frameworkVersionDir,
      dst: path.join(internalDir, 'Python.framework', 'Versions', 'Current'),
    },
  ];

  let changed = false;
  for (const target of targets) {
    changed = copyIfMissing(target.src, target.dst, logger) || changed;
  }

  try {
    fs.chmodSync(binaryPath, 0o755);
  } catch {
    // Best effort only.
  }
  return { changed };
}

module.exports = {
  ensureDarwinArm64RuntimeLayout,
};
