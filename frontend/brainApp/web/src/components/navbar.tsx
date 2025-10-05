"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, LayoutDashboard, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

export function Navbar() {
  const pathname = usePathname();

  return (
    <motion.nav
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="sticky top-4 z-50 w-full px-4"
    >
      <div className="glass-card rounded-2xl shadow-2xl border border-primary/20 mx-auto max-w-7xl">
        <div className="flex flex-row items-center w-full h-16 px-6 gap-4">
          <Link
            href="/"
            className="flex items-center gap-2 font-mono text-xl font-bold text-foreground transition-all duration-300 hover:scale-105 tracking-tight group"
          >
            <Sparkles className="h-5 w-5 text-primary group-hover:text-accent transition-colors terminal-glow" />
            <span className="code-accent">Synapse</span>
          </Link>

          <div className="flex-1 flex items-center justify-center gap-2">
            <Link
              href="/chat"
              className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium font-mono transition-all duration-300 ${
                pathname === "/chat"
                  ? "bg-primary/20 text-primary shadow-lg glow-primary scale-105"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground hover:scale-105"
              }`}
              style={{
                textShadow:
                  pathname === "/chat"
                    ? "0 0 10px rgba(147,197,253,0.5), 0 0 20px rgba(147,197,253,0.3)"
                    : "none",
              }}
            >
              <MessageSquare className="h-4 w-4" />
              <span className="drop-shadow-[0_0_8px_rgba(147,197,253,0.4)]">
                Chat
              </span>
            </Link>

            <Link
              href="/dashboard"
              className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium font-mono transition-all duration-300 ${
                pathname === "/dashboard"
                  ? "bg-primary/20 text-primary shadow-lg glow-primary scale-105"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground hover:scale-105"
              }`}
              style={{
                textShadow:
                  pathname === "/dashboard"
                    ? "0 0 10px rgba(147,197,253,0.5), 0 0 20px rgba(147,197,253,0.3)"
                    : "none",
              }}
            >
              <LayoutDashboard className="h-4 w-4" />
              <span className="drop-shadow-[0_0_8px_rgba(147,197,253,0.4)]">
                Dashboard
              </span>
            </Link>
          </div>
        </div>
      </div>
    </motion.nav>
  );
}
