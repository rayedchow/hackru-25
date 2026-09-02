import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("Next capture adapter defaults to loopback and never caches raw images", () => {
  const source = read("frontend/brainApp/web/src/app/api/screenshot/route.ts");

  assert.match(source, /http:\/\/127\.0\.0\.1:8000/);
  assert.match(source, /SYNAPSE_REMOTE_CAPTURE_ENABLED/);
  assert.match(source, /base\.protocol !== "https:"/);
  assert.match(source, /AbortSignal\.timeout\(10_000\)/);
  assert.match(source, /trustedBrowserRequest/);
  assert.match(source, /LOCAL_ORIGINS/);
  assert.doesNotMatch(source, /writeFile|latest\.png|public\/latest/);
});

test("active local listeners and screenshot websocket are loopback and origin constrained", () => {
  const server = read("frontend/brainApp/web/server.js");
  const electron = read("frontend/brainApp/web/electron/main.js");

  assert.match(server, /SYNAPSE_WEB_BIND_HOST \|\| "127\.0\.0\.1"/);
  assert.match(server, /server\.listen\(port, hostname/);
  assert.match(server, /allowedOrigins\.has\(origin\)/);
  assert.match(electron, /listen\(3001, "127\.0\.0\.1"/);
  assert.match(electron, /untrusted_origin/);
});

test("macOS capture streams bytes in memory to local services", () => {
  const source = read("frontend/brainApp/screenshot_app.py");

  assert.match(source, /"screencapture", "-i", "-t", "png", "-"/);
  assert.match(source, /BytesIO\(result\.stdout\)/);
  assert.match(source, /127\.0\.0\.1:3000\/api\/screenshot/);
  assert.doesNotMatch(source, /\/tmp\/screenshot|latest\.png/);
});

test("iOS capture has no committed destination or cleartext transport exception", () => {
  const swift = read("nourishment/nourishment/nourishmentBroadcast/SampleHandler.swift");
  const plist = read("nourishment/nourishment/nourishmentBroadcast/Info.plist");

  assert.match(swift, /SynapseUploadURL/);
  assert.match(swift, /url\.scheme == "https"/);
  assert.match(plist, /\$\(SYNAPSE_UPLOAD_URL\)/);
  assert.doesNotMatch(`${swift}\n${plist}`, /ngrok|NSAllowsArbitraryLoads/i);
  assert.doesNotMatch(swift, /http:\/\//i);
});

test("raw preview endpoint reports its narrow cache scope", () => {
  const route = read("frontend/brainApp/web/src/app/api/screenshot/route.ts");
  const viewer = read("frontend/brainApp/web/src/components/screenshot-viewer.tsx");

  assert.match(route, /base64: null/);
  assert.match(route, /scope: "web-adapter-cache"/);
  assert.match(route, /deleted: false/);
  assert.match(viewer, /Raw previews are not cached/);
});

test("active product copy states local defaults and labels prototype data", () => {
  const landing = read("frontend/brainApp/web/src/app/page.tsx");
  const layout = read("frontend/brainApp/web/src/app/layout.tsx");

  assert.match(landing, /Remote processing is off by default/);
  assert.match(landing, /Prototype visualization/);
  assert.match(landing, /127\.0\.0\.1:8000\/privacy/);
  assert.match(layout, /local-first screenshot memory/);
  assert.doesNotMatch(`${landing}\n${layout}`, /AI-powered analysis/);
});
