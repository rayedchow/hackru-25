import { NextRequest, NextResponse } from "next/server";

const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
const BACKEND_LOCAL_HOSTS = new Set(["127.0.0.1", "localhost"]);
const LOCAL_ORIGINS = new Set(["http://127.0.0.1:3000", "http://localhost:3000"]);
const LOCAL_HOST_PATTERN = /^(?:(?:127\.0\.0\.1|localhost)(?::\d{1,5})?|\[::1\](?::\d{1,5})?)$/;

function trustedBrowserRequest(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host") ?? "";
  return (!origin || LOCAL_ORIGINS.has(origin)) && LOCAL_HOST_PATTERN.test(host);
}

function backendUploadUrl(): URL {
  const configured = process.env.SYNAPSE_BACKEND_URL ?? "http://127.0.0.1:8000";
  const base = new URL(configured);
  const isLocal = BACKEND_LOCAL_HOSTS.has(base.hostname);
  const remoteOptIn = process.env.SYNAPSE_REMOTE_CAPTURE_ENABLED === "true";
  if (!isLocal && (!remoteOptIn || base.protocol !== "https:")) {
    throw new Error(
      "A non-local Synapse backend requires explicit remote capture opt-in and HTTPS.",
    );
  }
  return new URL("/upload", base);
}

export async function POST(request: NextRequest) {
  if (!trustedBrowserRequest(request)) {
    return NextResponse.json({ error: "Untrusted local browser request" }, { status: 403 });
  }
  try {
    const formData = await request.formData();
    const candidate = formData.get("image");
    if (!(candidate instanceof File)) {
      return NextResponse.json({ error: "No image file provided" }, { status: 400 });
    }
    if (!candidate.type.startsWith("image/")) {
      return NextResponse.json({ error: "Unsupported media type" }, { status: 415 });
    }
    if (candidate.size < 1 || candidate.size > MAX_UPLOAD_BYTES) {
      return NextResponse.json({ error: "Image size is outside the allowed range" }, { status: 413 });
    }

    const bytes = Buffer.from(await candidate.arrayBuffer());
    const response = await fetch(backendUploadUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        type: "video",
        payload: bytes.toString("base64"),
        source: "desktop-hotkey",
      }),
      signal: AbortSignal.timeout(10_000),
      cache: "no-store",
    });
    const result = await response.json();
    return NextResponse.json(result, { status: response.status });
  } catch (error) {
    console.error("Local encrypted screenshot ingestion failed", error);
    return NextResponse.json(
      { error: "Local encrypted screenshot ingestion failed" },
      { status: 502 },
    );
  }
}

export async function GET() {
  return NextResponse.json({
    url: null,
    base64: null,
    storage: "encrypted-backend",
    message: "Raw screenshot previews are not durably retained by the web adapter.",
  });
}

export async function DELETE() {
  return NextResponse.json({
    deleted: false,
    scope: "web-adapter-cache",
    alreadyAbsent: true,
    message:
      "The web adapter retains no raw screenshot. Delete encrypted memories by source ID through the privacy status page.",
  });
}
