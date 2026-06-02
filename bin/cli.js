#!/usr/bin/env node
"use strict";

/**
 * Cross-platform launcher for the SEC EDGAR MCP server.
 *
 * The server is Python (FastMCP). This wrapper lets it run via
 * `npx -y edgar-mcp` by locating Python 3.10+, building an isolated venv,
 * installing deps on first run, and spawning the server with stdio inherited.
 *
 * SEC_USER_AGENT (set in the MCP client config) is inherited automatically.
 *
 * IMPORTANT: stdout is the MCP protocol channel. Never write to it; logs -> stderr.
 */

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");

const PKG_ROOT = path.resolve(__dirname, "..");
const SERVER = path.join(PKG_ROOT, "edgar_mcp.py");
const REQUIREMENTS = path.join(PKG_ROOT, "requirements.txt");

function log(m) { process.stderr.write(`[edgar-mcp] ${m}\n`); }
function die(m, c = 1) { log(m); process.exit(c); }

function probePython(cmd) {
  try {
    const r = spawnSync(cmd, ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"], { encoding: "utf8" });
    if (r.status === 0 && r.stdout) {
      const [maj, min] = r.stdout.trim().split(".").map(Number);
      if (maj > 3 || (maj === 3 && min >= 10)) return { cmd, version: r.stdout.trim() };
    }
  } catch (_) {}
  return null;
}

function findPython() {
  const cands = process.platform === "win32" ? ["python", "py", "python3"] : ["python3", "python"];
  for (const c of cands) { const f = probePython(c); if (f) return f; }
  return null;
}

function venvPython(venvDir) {
  return process.platform === "win32"
    ? path.join(venvDir, "Scripts", "python.exe")
    : path.join(venvDir, "bin", "python");
}

function reqHash() {
  try { return crypto.createHash("sha256").update(fs.readFileSync(REQUIREMENTS)).digest("hex").slice(0, 16); }
  catch (_) { return "norequirements"; }
}

function ensureEnv() {
  const base = process.env.EDGAR_MCP_HOME || path.join(os.homedir() || os.tmpdir(), ".cache", "edgar-mcp");
  const venvDir = path.join(base, "venv");
  const py = venvPython(venvDir);
  const sentinel = path.join(venvDir, `.deps-${reqHash()}`);
  if (fs.existsSync(py) && fs.existsSync(sentinel)) return py;

  const sys = findPython();
  if (!sys) die("Python 3.10+ is required but was not found.\nInstall it from https://www.python.org/downloads/ and ensure `python3` (or `python`) is on PATH.");
  log(`Using ${sys.cmd} (Python ${sys.version}).`);
  fs.mkdirSync(base, { recursive: true });
  if (!fs.existsSync(py)) {
    log("First run: creating an isolated Python environment (one-time setup)...");
    if (spawnSync(sys.cmd, ["-m", "venv", venvDir], { stdio: ["ignore", 2, 2] }).status !== 0)
      die("Failed to create a Python virtual environment.");
  }
  log("Installing Python dependencies (mcp) - this may take a minute...");
  const pipArgs = ["-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", REQUIREMENTS];
  let pip = spawnSync(py, pipArgs, { stdio: ["ignore", 2, 2] });
  if (pip.status !== 0) {
    spawnSync(py, ["-m", "pip", "install", "--upgrade", "pip"], { stdio: ["ignore", 2, 2] });
    pip = spawnSync(py, pipArgs, { stdio: ["ignore", 2, 2] });
    if (pip.status !== 0) die("Failed to install Python dependencies. See errors above.");
  }
  fs.writeFileSync(sentinel, new Date().toISOString());
  log("Setup complete.");
  return py;
}

function main() {
  if (!fs.existsSync(SERVER)) die(`Server entry point not found: ${SERVER}`);
  const python = ensureEnv();
  const child = spawn(python, [SERVER, ...process.argv.slice(2)], { stdio: "inherit" });
  child.on("error", (e) => die(`Failed to start the server: ${e.message}`));
  child.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code == null ? 0 : code);
  });
  for (const sig of ["SIGINT", "SIGTERM"]) {
    process.on(sig, () => { try { child.kill(sig); } catch (_) {} });
  }
}

main();
