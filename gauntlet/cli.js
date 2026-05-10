#!/usr/bin/env node
// gauntlet/cli.js — thin shim that invokes the Python implementation.
//
// We want the CLI surface (`npx diwan preflight run ...`) without forcing a
// node sqlite dependency. The real runner is gauntlet/cli.py — this file
// just delegates so the bin entry in package.json works.

import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const pyScript = path.join(here, 'cli.py');
const args = process.argv.slice(2);

const child = spawn('python3', [pyScript, ...args], { stdio: 'inherit' });
child.on('exit', (code) => process.exit(code ?? 1));
child.on('error', (err) => {
  console.error('[diwan] failed to spawn python3:', err.message);
  process.exit(1);
});
