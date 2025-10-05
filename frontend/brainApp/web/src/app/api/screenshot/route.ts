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

    return NextResponse.json({
      url: `/latest.png?t=${Date.now()}`,
    });
  } catch (error) {
    return NextResponse.json({ url: null });
  }
}
