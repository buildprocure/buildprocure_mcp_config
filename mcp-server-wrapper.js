#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const pythonPath = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
const scriptPath = path.join(__dirname, 'mcp_server.py');

const pythonProcess = spawn(pythonPath, [scriptPath], {
  env: {
    ...process.env,
    GITHUB_USER: 'buildprocure',
    GITHUB_TOKEN: process.env.GITHUB_PAT
  }
});

pythonProcess.stdout.pipe(process.stdout);
pythonProcess.stderr.pipe(process.stderr);
pythonProcess.stdin.pipe(process.stdin);