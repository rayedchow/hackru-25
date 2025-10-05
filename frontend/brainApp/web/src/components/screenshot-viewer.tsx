"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Image as ImageIcon, Maximize2, Download } from "lucide-react";

export function ScreenshotViewer() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number>(Date.now());

  useEffect(() => {
    // Poll for new screenshot every second
    const interval = setInterval(() => {
      setLastUpdate(Date.now());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Check if screenshot exists
    fetch(`/api/screenshot?t=${lastUpdate}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.url && data.url !== imageUrl) {
          setImageUrl(data.url);

          // Notify Electron to show window if running in Electron
          if (typeof window !== "undefined" && (window as any).electron) {
            (window as any).electron.notifyScreenshot();
          }
        }
      })
      .catch(() => {});
  }, [lastUpdate, imageUrl]);

  return (
    <div className="flex h-full w-full flex-col bg-card">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-6 py-4">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-red-500/80" />
          <div className="h-3 w-3 rounded-full bg-yellow-500/80" />
          <div className="h-3 w-3 rounded-full bg-green-500/80" />
        </div>
        <h2 className="font-mono text-sm text-muted-foreground">
          Screenshot View
        </h2>
      </div>

      {/* Screenshot Display */}
      <div className="flex flex-1 items-center justify-center bg-background/50 p-4 overflow-auto">
        <AnimatePresence mode="wait">
          {imageUrl ? (
            <motion.div
              key={imageUrl}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.3 }}
              className="relative max-w-full max-h-full"
            >
              <img
                src={imageUrl}
                alt="Screenshot"
                className="w-full h-auto rounded-lg shadow-2xl border border-border/50"
                style={{
                  maxHeight: "calc(100vh - 300px)",
                  objectFit: "contain",
                }}
              />
              <div className="absolute top-2 right-2 flex gap-2">
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="p-2 rounded-lg bg-background/80 backdrop-blur-sm border border-border/50 hover:bg-background/90 transition-colors"
                  onClick={() => window.open(imageUrl, "_blank")}
                >
                  <Maximize2 className="h-4 w-4 text-foreground/70" />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="p-2 rounded-lg bg-background/80 backdrop-blur-sm border border-border/50 hover:bg-background/90 transition-colors"
                  onClick={() => {
                    const a = document.createElement("a");
                    a.href = imageUrl;
                    a.download = "screenshot.png";
                    a.click();
                  }}
                >
                  <Download className="h-4 w-4 text-foreground/70" />
                </motion.button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="placeholder"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center gap-4 text-center"
            >
              <div className="flex h-24 w-24 items-center justify-center rounded-full bg-card/50 backdrop-blur-sm border border-border/50">
                <ImageIcon className="h-12 w-12 text-foreground/30" />
              </div>
              <div>
                <p className="text-sm font-mono text-foreground/50">
                  No screenshot yet
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Press Command + J to capture
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
