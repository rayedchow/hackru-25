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
      className="sticky top-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-4xl px-4 mx-auto"
    >
      <div className="glass-card rounded-2xl shadow-2xl border border-primary/20">
        <div className="flex leading-7 px-[60px] flex-row justify-end w-auto h-16 items-center gap-1 mx-[-140px]">
          <Link
            href="/"
            className="flex items-center gap-2 font-mono text-xl font-bold text-foreground transition-all duration-300 hover:scale-105 tracking-tight group"
          >
            <Sparkles className="h-5 w-5 text-primary group-hover:text-accent transition-colors terminal-glow" />
            <span className="code-accent">Brain App</span>
          </Link>

          <div className="flex items-center gap-2">
            <Link
              href="/chat"
              className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium font-mono transition-all duration-300 ${
                pathname === "/chat"
                  ? "bg-primary/20 text-primary shadow-lg glow-primary scale-105 terminal-glow"
                  : "text-muted-foreground hover:bg-muted hover:text-primary hover:scale-105 hover:terminal-glow"
              }`}
            >
              <MessageSquare className="h-4 w-4" />
              <span>Chat</span>
            </Link>

            <Link
              href="/dashboard"
              className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium font-mono transition-all duration-300 ${
                pathname === "/dashboard"
                  ? "bg-primary/20 text-primary shadow-lg glow-primary scale-105 terminal-glow"
                  : "text-muted-foreground hover:bg-muted hover:text-primary hover:scale-105 hover:terminal-glow"
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              <span>Dashboard</span>
            </Link>
          </div>
        </div>
      </div>
    </motion.nav>
  );
}
