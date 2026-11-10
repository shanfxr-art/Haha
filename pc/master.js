"use strict";
// pc/master.js - runs on the Windows VM for one 6-hour cycle.
//   node pc/master.js          run the whole cycle (default)
//   node pc/master.js backup   one backup now (used by the workflow's always() step)
//   node pc/master.js restore  restore from Drive only
// Cycle: wait for the old VM -> restore from Drive -> install newest PC client -> run it under a watchdog
//        -> back up every few minutes -> at handoverMin stop the app, save a final backup, exit.
const fs = require("fs"), path = require("path"), cp = require("child_process");
const L = require("./lib");
const { env, log, sleep } = L;

const MODE = process.argv[2] || "run";
const WIN = process.platform === "win32";
const T0 = Date.now();
const DATA = env("JARVIS_DIR") || (WIN ? "C:\\JarvisPC" : path.join(__dirname, "..", "jarvis-data"));
const APP = path.join(DATA, "app"), WORK = path.join(DATA, "work"), TMP = path.join(DATA, "tmp");
const FINAL_FLAG = path.join(DATA, "final.done");

function readJson(f) { try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch (e) { return {}; } }
const CFG = Object.assign({ paths: ["%WORK%"], exclude: ["*.tmp", "Cache", "node_modules"], keep: 4, intervalMin: 20, handoverMin: 345, hubData: true, driveFolder: "JarvisPC", releasePattern: "^Jarvis-PC.*\\.zip$", waitForOldVmMin: 12 }, readJson(path.join(__dirname, "backup.json")));
const expand = s => String(s).replace(/%(\w+)%/g, (m, k) => k === "WORK" ? WORK : k === "DATA" ? DATA : (process.env[k] || m));
const PATHS = CFG.paths.map(expand);
const SECRET = env("PC_TOKEN");   // the backup key; the same value lives only in the repo secrets and the hub config

let stopping = false;

// ---------- backup ----------
async function backup(why) {
  if (!L.driveReady()) { log("backup skipped: the three GDRIVE_* secrets are not set"); return false; }
  if (!SECRET) { log("backup skipped: PC_TOKEN is not set (it is the encryption key)"); return false; }
  try {
    fs.rmSync(TMP, { recursive: true, force: true });
    const stage = path.join(TMP, "stage"); fs.mkdirSync(stage, { recursive: true });
    if (CFG.hubData && env("HUB_URL")) {
      try {
        const r = await L.http(env("HUB_URL").replace(/\/+$/, "") + "/v1/pc/hubdata", { headers: { Authorization: "Bearer " + SECRET } }, 2);
        if (r.ok) { const j = await r.json(); fs.writeFileSync(path.join(stage, "hub-data.json"), String(j.data || "")); }
        else log("hub data not saved (hub answered " + r.status + "; replace the hub files first)");
      } catch (e) { log("hub data not saved:", e.message); }
    }
    const tgz = path.join(TMP, "b.tgz"), enc = path.join(TMP, "b.jpc");
    const n = L.packFolders(PATHS, CFG.exclude, stage, tgz);
    L.encryptFile(tgz, enc, SECRET);
    const d = new Date(), p2 = x => String(x).padStart(2, "0");
    const name = "pcbak-" + d.getUTCFullYear() + p2(d.getUTCMonth() + 1) + p2(d.getUTCDate()) + "-" + p2(d.getUTCHours()) + p2(d.getUTCMinutes()) + p2(d.getUTCSeconds()) + (why === "final" ? "-final" : "") + ".jpc";
    const folder = await L.driveFolder(CFG.driveFolder);
    await L.driveUpload(folder, name, enc);
    const files = (await L.driveList(folder)).filter(f => /^pcbak-.*\.jpc$/.test(f.name));
    for (const f of files.slice(Math.max(1, CFG.keep))) await L.driveDelete(f.id).catch(() => {});
    log("backup saved:", name, Math.round(fs.statSync(enc).size / 1024) + " KB,", n + " folder(s)");
    return true;
  } catch (e) { log("backup failed:", e.message); return false; }
  finally { fs.rmSync(TMP, { recursive: true, force: true }); }
}

// ---------- restore ----------
async function restore() {
  if (!L.driveReady() || !SECRET) { log("restore skipped: Drive secrets or PC_TOKEN missing"); return false; }
  try {
    const folder = await L.driveFolder(CFG.driveFolder);
    const f = (await L.driveList(folder)).find(x => /^pcbak-.*\.jpc$/.test(x.name));
    if (!f) { log("restore: no backup on Drive yet (first run)"); return false; }
    fs.mkdirSync(TMP, { recursive: true });
    const enc = path.join(TMP, "r.jpc"), tgz = path.join(TMP, "r.tgz");
    await L.driveDownload(f.id, enc);
    L.decryptFile(enc, tgz, SECRET);
    const n = L.unpackFolders(tgz, path.join(TMP, "x"));
    const hub = path.join(TMP, "x", "hub-data.json");
    if (fs.existsSync(hub)) { fs.mkdirSync(WORK, { recursive: true }); fs.copyFileSync(hub, path.join(WORK, "hub-data.restore.json")); }
    log("restored", f.name + ":", n + " folder(s)");
    return true;
  } catch (e) { log("restore failed:", e.message); return false; }
  finally { fs.rmSync(TMP, { recursive: true, force: true }); }
}

// ---------- PC client ----------
let installedN = 0;
async function installClient() {
  const repo = env("PC_RELEASE_REPO"), token = env("PC_RELEASE_TOKEN");
  if (!repo) { log("client: PC_RELEASE_REPO is not set, nothing to download"); return false; }
  try {
    const rel = await L.findPcRelease(repo, token, CFG.releasePattern);
    if (!rel) { log("client: no release with a PC client yet"); return false; }
    fs.mkdirSync(TMP, { recursive: true });
    const zip = path.join(TMP, "client.zip");
    await L.downloadAsset(rel.asset, token, zip);
    if (rel.sha) {
      const want = ((await L.assetText(rel.sha, token)).match(/[a-f0-9]{64}/i) || [""])[0].toLowerCase(), got = L.sha256File(zip);
      if (want !== got) { log("client: checksum mismatch, NOT installing"); return false; }
      log("client: checksum ok");
    } else log("client: no .sha256 next to the asset, installing without a check");
    fs.rmSync(APP, { recursive: true, force: true });
    L.unzip(zip, APP);
    installedN = rel.n || 0;
    log("client installed:", rel.asset.name, "(" + rel.tag + ")");
    return true;
  } catch (e) { log("client install failed:", e.message); return false; }
  finally { fs.rmSync(TMP, { recursive: true, force: true }); }
}

function findEntry() {
  const names = WIN ? ["jarvis-pc.exe", "start.cmd", "start.bat"] : ["start.sh"];
  const dirs = [APP];
  try { for (const d of fs.readdirSync(APP, { withFileTypes: true })) if (d.isDirectory()) dirs.push(path.join(APP, d.name)); } catch (e) { return null; }
  for (const d of dirs) for (const n of names) { const p = path.join(d, n); if (fs.existsSync(p)) return p; }
  return null;
}

// ---------- watchdog ----------
let child = null, restarts = 0, startedAt = 0, nextTry = 0;
function startApp(entry) {
  const opt = { cwd: path.dirname(entry), windowsHide: false, env: Object.assign({}, process.env, { JARVIS_DATA: WORK, HUB_URL: env("HUB_URL"), PC_TOKEN: env("PC_TOKEN") }) };
  const isCmd = /\.(cmd|bat)$/i.test(entry);
  child = isCmd ? cp.spawn("cmd.exe", ["/c", entry], opt) : (entry.endsWith(".sh") ? cp.spawn("sh", [entry], opt) : cp.spawn(entry, [], opt));
  startedAt = Date.now();
  const pipe = s => s.on("data", d => String(d).split(/\r?\n/).filter(Boolean).slice(-20).forEach(l => log("[app]", l.slice(0, 300))));
  pipe(child.stdout); pipe(child.stderr);
  child.on("exit", c => { log("app exited with code", c); child = null; });
  child.on("error", e => { log("app failed to start:", e.message); child = null; });
  log("app started");
}
function watch(entry) {
  if (stopping || child || Date.now() < nextTry) return;
  if (Date.now() - startedAt > 300000) restarts = 0;   // it ran 5 minutes: forget earlier crashes
  nextTry = Date.now() + Math.min(5000 * Math.pow(2, restarts), 60000); restarts++;
  startApp(entry);
}
async function updateIfNewer() {   // a newer PC build was released: install it and let the watchdog restart the app
  try {
    const rel = await L.findPcRelease(env("PC_RELEASE_REPO"), env("PC_RELEASE_TOKEN"), CFG.releasePattern);
    if (!rel || !(rel.n > installedN)) return;
    log("update: build", rel.n, "is newer than", installedN, "- installing");
    if (child) { try { if (WIN) cp.spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore" }); else child.kill("SIGTERM"); } catch (e) {} child = null; }
    if (await installClient()) { nextTry = 0; restarts = 0; }
  } catch (e) { log("update check failed:", e.message); }
}
function stopApp() {
  stopping = true;
  if (!child) return;
  try { if (WIN) cp.spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore" }); else child.kill("SIGTERM"); } catch (e) {}
  child = null;
}

async function hubPing() {
  if (!env("HUB_URL") || !SECRET) { log("hub: HUB_URL or PC_TOKEN missing"); return; }
  try {
    const r = await L.http(env("HUB_URL").replace(/\/+$/, "") + "/v1/pc/info", { headers: { Authorization: "Bearer " + SECRET } }, 2);
    log(r.ok ? "hub reachable, token accepted" : "hub answered " + r.status + " (check HUB_URL and PC_TOKEN)");
  } catch (e) { log("hub not reachable:", e.message); }
}

async function waitForOldVm() {
  const until = Date.now() + CFG.waitForOldVmMin * 60000;
  let waited = false;
  try {
    while (Date.now() < until && (await L.otherActiveRuns()) > 0) {
      if (!waited) log("waiting for the previous VM to finish its final backup"); waited = true;
      await sleep(20000);
    }
  } catch (e) { log("could not check the previous run:", e.message); }
  if (waited) log("previous VM is done (or the wait ran out), continuing");
}

async function finish() {
  if (fs.existsSync(FINAL_FLAG)) return;
  stopApp();
  await backup("final");
  try { fs.mkdirSync(DATA, { recursive: true }); fs.writeFileSync(FINAL_FLAG, new Date().toISOString()); } catch (e) {}
}

// ---------- main ----------
(async () => {
  fs.mkdirSync(WORK, { recursive: true });
  if (MODE === "backup") { await (fs.existsSync(FINAL_FLAG) ? Promise.resolve(log("final backup already done")) : backup("manual")); return; }
  if (MODE === "restore") { await restore(); return; }

  log("master starting; data folder", DATA);
  await waitForOldVm();
  await restore();
  await installClient();
  await hubPing();

  let entry = findEntry();
  if (!entry) log("no PC client found yet; the VM stays up and backups keep running");

  process.on("SIGTERM", async () => { await finish(); process.exit(0); });
  process.on("SIGINT", async () => { await finish(); process.exit(0); });

  let lastBackup = Date.now(), lastUpdate = Date.now();
  const handoverAt = T0 + (Number(env("PC_HANDOVER_MIN")) || CFG.handoverMin) * 60000;
  while (Date.now() < handoverAt) {
    if (Date.now() - lastUpdate >= 300000) { lastUpdate = Date.now(); await updateIfNewer(); entry = findEntry(); }
    if (entry) watch(entry);
    if (Date.now() - lastBackup >= CFG.intervalMin * 60000) { lastBackup = Date.now(); await backup("timer"); }
    await sleep(15000);
  }
  log("handover time: stopping the app and saving the final backup");
  await finish();
  log("master done");
  process.exit(0);
})().catch(e => { log("master crashed:", e.message); process.exit(1); });
