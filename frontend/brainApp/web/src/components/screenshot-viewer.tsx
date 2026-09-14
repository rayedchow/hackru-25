"use client";

import { LockKeyhole, ShieldCheck } from "lucide-react";

export function ScreenshotViewer() {
  return (
    <section
      className="flex h-full w-full flex-col bg-card"
      aria-labelledby="capture-privacy-heading"
    >
      <div className="flex items-center gap-3 border-b border-border px-6 py-4">
        <ShieldCheck className="h-5 w-5 text-emerald-400" aria-hidden="true" />
        <h2
          id="capture-privacy-heading"
          className="font-mono text-sm text-foreground"
        >
          Encrypted capture
        </h2>
      </div>
      <div className="flex flex-1 items-center justify-center bg-background/50 p-6">
        <div className="max-w-sm text-center">
          <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full border border-emerald-400/40 bg-emerald-400/10">
            <LockKeyhole className="h-9 w-9 text-emerald-300" aria-hidden="true" />
          </div>
          <p className="font-mono text-sm text-foreground">
            Raw previews are not cached in the web app.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            Command + J sends an in-memory image to your configured Synapse
            backend, where it is encrypted before durable storage.
          </p>
          <a
            href="http://127.0.0.1:8000/privacy"
            className="mt-5 inline-flex rounded-md border border-border px-3 py-2 text-xs font-mono text-foreground outline-none hover:bg-background focus-visible:ring-2 focus-visible:ring-primary"
          >
            Open privacy status
          </a>
        </div>
      </div>
    </section>
  );
}
