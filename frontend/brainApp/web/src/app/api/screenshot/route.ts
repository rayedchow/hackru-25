import { NextRequest, NextResponse } from "next/server";
import { writeFile, readFile, stat } from "fs/promises";
import path from "path";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("image") as File;

    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);

    // Save to public directory
    const filePath = path.join(process.cwd(), "public", "latest.png");
    await writeFile(filePath, buffer);

    // Notify WebSocket clients
    try {
      if (typeof (global as any).broadcastScreenshotUpdate === "function") {
        (global as any).broadcastScreenshotUpdate();
      }
    } catch (error) {
      console.log("Could not broadcast screenshot update:", error);
      // Non-fatal, continue
    }

    // Also notify Electron if it's running
    try {
      await fetch("http://localhost:3001/electron/show", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
    } catch {
      // Electron not running, that's fine
    }

    return NextResponse.json({
      success: true,
      url: `/latest.png?t=${Date.now()}`,
    });
  } catch (error) {
    console.error("Error uploading screenshot:", error);
    return NextResponse.json({ error: "Upload failed" }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const filePath = path.join(process.cwd(), "public", "latest.png");

    // Check if file exists
    await stat(filePath);

    // Check if we need to return base64
    const searchParams = request.nextUrl.searchParams;
    const asBase64 = searchParams.get("base64") === "true";

    if (asBase64) {
      const buffer = await readFile(filePath);
      const base64 = buffer.toString("base64");
      return NextResponse.json({
        base64,
      });
    }

    return NextResponse.json({
      url: `/latest.png?t=${Date.now()}`,
    });
  } catch (error) {
    return NextResponse.json({ url: null, base64: null });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const { unlink } = await import("fs/promises");
    const filePath = path.join(process.cwd(), "public", "latest.png");
    await unlink(filePath);
    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ success: false, error: "File not found" }, { status: 404 });
  }
}
