"use strict";
// pc/lib.js - helpers for master.js. No npm dependencies. Needs Node 18+ (global fetch).
const fs = require("fs"), path = require("path"), crypto = require("crypto"), cp = require("child_process");

const env = k => String(process.env[k] || "");
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SECRETS = ["PC_TOKEN", "GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN", "GH_TOKEN", "PC_RELEASE_TOKEN", "RDP_PASSWORD", "TS_AUTHKEY"];
// Never let a secret reach the (public) workflow log.
function redact(s) {
  s = String(s);
  for (const k of SECRETS) { const v = env(k); if (v.length >= 6) s = s.split(v).join("***"); }
  return s;
}
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), redact(a.join(" ")));

async function http(url, opt = {}, tries = 3) {
  let err;
  for (let i = 0; i < tries; i++) {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), opt.timeout || 60000);
    try {
      const r = await fetch(url, Object.assign({}, opt, { signal: ctl.signal }));
      if ((r.status >= 500 || r.status === 429) && i < tries - 1) { err = new Error("HTTP " + r.status); await sleep(1500 * (i + 1)); continue; }
      return r;
    } catch (e) { err = new Error(String(e.message || e).replace(/https?:\/\/\S+/g, "<url>")); if (i < tries - 1) await sleep(1500 * (i + 1)); }
    finally { clearTimeout(t); }
  }
  throw err;
}

// ---------- tar / zip (Windows 10+ and Windows Server ship bsdtar) ----------
function tarBin() {
  if (process.platform === "win32") { const p = (process.env.SystemRoot || "C:\\Windows") + "\\System32\\tar.exe"; if (fs.existsSync(p)) return p; }
  return "tar";
}
function run(cmd, args, opt = {}) { return cp.spawnSync(cmd, args, Object.assign({ stdio: "pipe", windowsHide: true, maxBuffer: 1 << 26 }, opt)); }
function unzip(file, dest) {
  fs.mkdirSync(dest, { recursive: true });
  const r = process.platform === "win32" ? run(tarBin(), ["-xf", file, "-C", dest]) : run("unzip", ["-q", "-o", file, "-d", dest]);
  if (r.status !== 0) throw new Error("unzip failed: " + String(r.stderr || "").slice(0, 200));
}

// ---------- encryption (AES-256-GCM, key from a secret via scrypt) ----------
function encryptFile(src, dst, secret) {
  const salt = crypto.randomBytes(16), iv = crypto.randomBytes(12), key = crypto.scryptSync(secret, salt, 32);
  const c = crypto.createCipheriv("aes-256-gcm", key, iv);
  const body = Buffer.concat([c.update(fs.readFileSync(src)), c.final()]);
  fs.writeFileSync(dst, Buffer.concat([Buffer.from("JPC1"), salt, iv, body, c.getAuthTag()]));
}
function decryptFile(src, dst, secret) {
  const b = fs.readFileSync(src);
  if (b.length < 48 || b.slice(0, 4).toString() !== "JPC1") throw new Error("not a Jarvis PC backup");
  const key = crypto.scryptSync(secret, b.slice(4, 20), 32), d = crypto.createDecipheriv("aes-256-gcm", key, b.slice(20, 32));
  d.setAuthTag(b.slice(b.length - 16));
  fs.writeFileSync(dst, Buffer.concat([d.update(b.slice(32, b.length - 16)), d.final()]));
}

// ---------- Google Drive (OAuth refresh token, resumable upload) ----------
const DRIVE = () => env("DRIVE_API") || "https://www.googleapis.com/drive/v3";
const UPLOAD = () => env("DRIVE_UPLOAD") || "https://www.googleapis.com/upload/drive/v3";
const TOKEN_URL = () => env("GDRIVE_TOKEN_URL") || "https://oauth2.googleapis.com/token";
const driveReady = () => !!(env("GDRIVE_CLIENT_ID") && env("GDRIVE_CLIENT_SECRET") && env("GDRIVE_REFRESH_TOKEN"));
let tok = { v: "", exp: 0 };
async function driveToken() {
  if (tok.v && Date.now() < tok.exp - 60000) return tok.v;
  const body = new URLSearchParams({ client_id: env("GDRIVE_CLIENT_ID"), client_secret: env("GDRIVE_CLIENT_SECRET"), refresh_token: env("GDRIVE_REFRESH_TOKEN"), grant_type: "refresh_token" });
  const r = await http(TOKEN_URL(), { method: "POST", body });
  const j = await r.json().catch(() => ({}));
  if (!j.access_token) throw new Error("Drive refused the refresh token (" + (j.error || r.status) + ")");
  tok = { v: j.access_token, exp: Date.now() + (j.expires_in || 3000) * 1000 };
  return tok.v;
}
async function dapi(p, opt = {}) {
  const t = await driveToken();
  return http(DRIVE() + p, Object.assign({}, opt, { headers: Object.assign({ Authorization: "Bearer " + t }, opt.headers || {}) }));
}
async function driveFolder(name) {
  const q = encodeURIComponent("name='" + name.replace(/['\\]/g, "\\$&") + "' and mimeType='application/vnd.google-apps.folder' and trashed=false");
  let r = await dapi("/files?q=" + q + "&fields=files(id)&spaces=drive"), j = await r.json().catch(() => ({}));
  if (j.files && j.files[0]) return j.files[0].id;
  r = await dapi("/files?fields=id", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, mimeType: "application/vnd.google-apps.folder" }) });
  j = await r.json().catch(() => ({}));
  if (!j.id) throw new Error("cannot create the Drive folder (" + r.status + ")");
  return j.id;
}
async function driveList(folder) {
  const q = encodeURIComponent("'" + folder + "' in parents and trashed=false");
  const r = await dapi("/files?q=" + q + "&pageSize=200&fields=files(id,name,size)"), j = await r.json().catch(() => ({}));
  return (j.files || []).sort((a, b) => (a.name < b.name ? 1 : -1));   // newest first (names carry a timestamp)
}
async function driveUpload(folder, name, file) {
  const t = await driveToken(), size = fs.statSync(file).size;
  const init = await http(UPLOAD() + "/files?uploadType=resumable&fields=id", { method: "POST", headers: { Authorization: "Bearer " + t, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Length": String(size) }, body: JSON.stringify({ name, parents: [folder] }) });
  const loc = init.headers.get("location");
  if (!loc) throw new Error("Drive refused the upload (" + init.status + ")");
  const r = await http(loc, { method: "PUT", body: fs.readFileSync(file), timeout: 900000 });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.id) throw new Error("Drive upload failed (" + r.status + ")");
  return j.id;
}
async function driveDownload(id, file) {
  const r = await dapi("/files/" + encodeURIComponent(id) + "?alt=media", { timeout: 900000 });
  if (!r.ok) throw new Error("Drive download failed (" + r.status + ")");
  fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
}
async function driveDelete(id) { await dapi("/files/" + encodeURIComponent(id), { method: "DELETE" }); }

// ---------- backup / restore of folders ----------
// Archive layout: manifest.json, hub-data.json (optional), and each folder stored under its own name.
function packFolders(paths, exclude, extraDir, out) {
  const seen = new Set(), entries = [], args = ["-czf", out];
  for (const x of exclude || []) args.push("--exclude", x);
  args.push("-C", extraDir, ".");
  for (const p of paths) {
    if (!fs.existsSync(p)) continue;
    const parent = path.dirname(p), name = path.basename(p);
    if (seen.has(name.toLowerCase())) { log("backup: skipping", p, "(same folder name as another entry)"); continue; }
    seen.add(name.toLowerCase()); entries.push({ parent, name });
    args.push("-C", parent, name);
  }
  fs.writeFileSync(path.join(extraDir, "manifest.json"), JSON.stringify({ at: new Date().toISOString(), entries }));
  const r = run(tarBin(), args);
  // bsdtar returns 1 for "some file was busy"; the archive is still good.
  if (r.status > 1 || !fs.existsSync(out) || fs.statSync(out).size < 20) throw new Error("tar failed: " + String(r.stderr || "").slice(0, 200));
  return entries.length;
}
function unpackFolders(archive, tmpDir) {
  fs.rmSync(tmpDir, { recursive: true, force: true }); fs.mkdirSync(tmpDir, { recursive: true });
  const r = run(tarBin(), ["-xzf", archive, "-C", tmpDir]);
  if (r.status > 1) throw new Error("untar failed: " + String(r.stderr || "").slice(0, 200));
  const m = JSON.parse(fs.readFileSync(path.join(tmpDir, "manifest.json"), "utf8"));
  let n = 0;
  for (const e of m.entries || []) {
    const from = path.join(tmpDir, e.name);
    if (!fs.existsSync(from)) continue;
    fs.mkdirSync(e.parent, { recursive: true });
    fs.cpSync(from, path.join(e.parent, e.name), { recursive: true, force: true }); n++;
  }
  return n;
}

// ---------- GitHub: PC client release, other active runs ----------
const GH = () => env("GITHUB_API") || "https://api.github.com";
const ghHeaders = (t, extra) => Object.assign({ Accept: "application/vnd.github+json", "User-Agent": "jarvis-pc" }, t ? { Authorization: "Bearer " + t } : {}, extra || {});
async function findPcRelease(repo, token, pattern) {
  const r = await http(GH() + "/repos/" + repo + "/releases?per_page=100", { headers: ghHeaders(token) });
  if (!r.ok) throw new Error("release list failed (" + r.status + ")");
  const re = new RegExp(pattern, "i");
  let best = null, bestN = -1;   // GitHub's list order can shuffle (tags on the same commit), so take the highest build number instead
  for (const rel of await r.json()) {
    const a = (rel.assets || []).find(x => re.test(x.name));
    if (!a) continue;
    const m = /build(\d+)/i.exec(a.name) || /(\d+)$/.exec(rel.tag_name || ""), n = m ? Number(m[1]) : 0;
    if (n > bestN) { bestN = n; best = { n, tag: rel.tag_name, asset: a, sha: (rel.assets || []).find(x => x.name === a.name + ".sha256") || null }; }
  }
  log("client: newest PC build on GitHub is", bestN);
  return best;
}
async function downloadAsset(asset, token, file) {
  const r = await http(asset.url, { headers: ghHeaders(token, { Accept: "application/octet-stream" }), timeout: 600000 });
  if (!r.ok) throw new Error("download failed (" + r.status + ")");
  fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
}
async function assetText(asset, token) {
  const r = await http(asset.url, { headers: ghHeaders(token, { Accept: "application/octet-stream" }) });
  return r.ok ? await r.text() : "";
}
const sha256File = f => crypto.createHash("sha256").update(fs.readFileSync(f)).digest("hex");

// Other runs of this workflow that are still going (the previous VM, during the 6-hour handover).
async function otherActiveRuns() {
  const repo = env("GITHUB_REPOSITORY"), run = env("GITHUB_RUN_ID"), t = env("GH_TOKEN");
  if (!repo || !run || !t) return 0;
  const me = await (await http(GH() + "/repos/" + repo + "/actions/runs/" + run, { headers: ghHeaders(t) })).json().catch(() => ({}));
  if (!me.workflow_id) return 0;
  const j = await (await http(GH() + "/repos/" + repo + "/actions/workflows/" + me.workflow_id + "/runs?status=in_progress&per_page=30", { headers: ghHeaders(t) })).json().catch(() => ({}));
  return (j.workflow_runs || []).filter(x => String(x.id) !== run).length;
}

module.exports = { env, sleep, log, redact, http, run, tarBin, unzip, encryptFile, decryptFile, driveReady, driveFolder, driveList, driveUpload, driveDownload, driveDelete, packFolders, unpackFolders, findPcRelease, downloadAsset, assetText, sha256File, otherActiveRuns };
