"use client";

import {
  motion,
  AnimatePresence,
  useInView,
  useAnimation,
} from "framer-motion";
import { useEffect, useRef } from "react";
import {
  Sparkles,
  BarChart3,
  Activity,
  Clock,
  Cpu,
  TrendingUp,
  Camera,
  Brain,
  Zap,
  Network,
} from "lucide-react";
import { KnowledgeGraph } from "@/components/knowledge-graph";
import { AnimatedBackground } from "@/components/animated-background";
import { Navbar } from "@/components/navbar";
import graphData from "@/a.json";

export default function DashboardPage() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const controls = useAnimation();

  useEffect(() => {
    if (inView) controls.start("visible");
  }, [inView, controls]);

  const metrics = [
    {
      icon: Camera,
      label: "Screenshots",
      value: 127,
      diff: "+12 this week",
      color: "text-sky-400",
    },
    {
      icon: Brain,
      label: "AI Sessions",
      value: 43,
      diff: "+8 this week",
      color: "text-purple-400",
    },
    {
      icon: Clock,
      label: "Time Saved",
      value: 2.4,
      diff: "Today",
      suffix: "h",
      color: "text-amber-400",
    },
    {
      icon: TrendingUp,
      label: "Efficiency",
      value: 94,
      diff: "+3% this week",
      suffix: "%",
      color: "text-green-400",
    },
  ];

  const activities = [
    { text: "Screenshot captured", time: "2 minutes ago", icon: Camera },
    { text: "AI analysis completed", time: "5 minutes ago", icon: Brain },
    { text: "Knowledge graph updated", time: "12 minutes ago", icon: Network },
    { text: "New insights generated", time: "45 minutes ago", icon: Zap },
    { text: "Settings updated", time: "1 hour ago", icon: Activity },
  ];

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AnimatedBackground />

      <div className="absolute inset-0 bg-background/40 backdrop-blur-xl" />

      <div className="relative z-10 flex flex-col h-full">
        <Navbar />

        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="flex-1 overflow-y-auto p-8"
        >
          {/* Header */}
          <div className="flex justify-between items-center mb-8">
            <motion.h1
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-4xl font-bold font-mono text-foreground terminal-glow flex items-center gap-3"
            >
              <Sparkles className="h-8 w-8 text-primary" />
              Dashboard
            </motion.h1>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="text-sm font-mono text-muted-foreground"
            >
              {new Date().toLocaleDateString("en-US", {
                weekday: "long",
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </motion.div>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
            {metrics.map((m, i) => (
              <motion.div
                key={m.label}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                whileHover={{ scale: 1.03, y: -4 }}
                className="p-6 rounded-2xl glass-card border border-primary/20 shadow-2xl glow-primary"
              >
                <div className="flex justify-between items-center mb-3">
                  <m.icon className={`${m.color} h-6 w-6`} />
                  <p className="text-xs text-muted-foreground font-mono">
                    {m.diff}
                  </p>
                </div>
                <h2 className="text-4xl font-bold font-mono text-foreground mb-1">
                  <motion.span
                    initial={{ textShadow: "0px 0px 0px rgba(0,0,0,0)" }}
                    animate={{
                      textShadow: `0px 0px 10px rgba(147,197,253,0.6), 0px 0px 20px rgba(147,197,253,0.3)`,
                    }}
                    transition={{
                      repeat: Infinity,
                      duration: 2,
                      repeatType: "mirror",
                    }}
                  >
                    {m.value}
                    {m.suffix ?? ""}
                  </motion.span>
                </h2>
                <p className="text-sm text-muted-foreground font-mono">
                  {m.label}
                </p>
              </motion.div>
            ))}
          </div>

          {/* Main Body */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            {/* Left - Activity Overview */}
            <motion.div
              ref={ref}
              variants={{
                hidden: { opacity: 0, y: 20 },
                visible: { opacity: 1, y: 0 },
              }}
              initial="hidden"
              animate={controls}
              transition={{ duration: 0.8 }}
              className="rounded-2xl glass-card border border-primary/20 p-6 shadow-xl"
            >
              <h3 className="text-lg font-semibold font-mono mb-5 flex items-center gap-2 text-foreground">
                <BarChart3 className="h-5 w-5 text-primary" /> Activity Overview
              </h3>

              {[
                { label: "Screenshots", value: 80, color: "bg-sky-500" },
                { label: "AI Chats", value: 60, color: "bg-purple-500" },
                { label: "Analysis", value: 90, color: "bg-amber-400" },
              ].map((bar, i) => (
                <div key={bar.label} className="mb-5">
                  <div className="flex justify-between mb-2 text-sm font-mono">
                    <p className="text-foreground/80">{bar.label}</p>
                    <p className="text-primary">{bar.value}%</p>
                  </div>
                  <div className="relative w-full h-2 rounded-full bg-muted overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      whileInView={{ width: `${bar.value}%` }}
                      transition={{
                        duration: 1.2,
                        delay: i * 0.2,
                        ease: "easeOut",
                      }}
                      className={`${bar.color} h-full rounded-full shadow-[0_0_15px_rgba(255,255,255,0.5)]`}
                    />
                  </div>
                </div>
              ))}
            </motion.div>

            {/* Right - Recent Activity */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
              className="lg:col-span-2 rounded-2xl glass-card border border-primary/20 p-6 shadow-xl"
            >
              <h3 className="text-lg font-semibold font-mono mb-5 flex items-center gap-2 text-foreground">
                <Clock className="h-5 w-5 text-primary" /> Recent Activity
              </h3>
              <ul className="space-y-4">
                <AnimatePresence>
                  {activities.map((a, i) => (
                    <motion.li
                      key={a.text}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.1 }}
                      whileHover={{ x: 4 }}
                      className="flex items-center justify-between text-sm font-mono p-3 rounded-lg bg-background/20 border border-border/30"
                    >
                      <span className="flex items-center gap-3">
                        <a.icon className="h-4 w-4 text-primary" />
                        <span className="text-foreground/90">{a.text}</span>
                      </span>
                      <span className="text-muted-foreground">{a.time}</span>
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            </motion.div>
          </div>

          {/* Knowledge Graph Section */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="mb-8"
          >
            <div className="flex items-center gap-2 mb-4">
              <Network className="h-6 w-6 text-primary" />
              <h2 className="text-2xl font-bold font-mono text-foreground terminal-glow">
                Knowledge Graph
              </h2>
              <span className="text-sm text-muted-foreground font-mono ml-2">
                Visual representation of your captured data
              </span>
            </div>
            <KnowledgeGraph nodes={graphData.nodes} edges={graphData.edges} />
          </motion.div>

          {/* Bottom Stats */}
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
          >
            <div className="glass-card rounded-2xl p-6 border border-primary/20 shadow-xl">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg bg-primary/20">
                  <Camera className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground font-mono">
                    Total Captures
                  </p>
                  <p className="text-2xl font-bold font-mono text-foreground">
                    1,247
                  </p>
                </div>
              </div>
              <p className="text-xs text-green-400 font-mono">
                ↑ 23% from last month
              </p>
            </div>

            <div className="glass-card rounded-2xl p-6 border border-primary/20 shadow-xl">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg bg-purple-500/20">
                  <Network className="h-5 w-5 text-purple-400" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground font-mono">
                    Graph Nodes
                  </p>
                  <p className="text-2xl font-bold font-mono text-foreground">
                    {graphData.nodes.length}
                  </p>
                </div>
              </div>
              <p className="text-xs text-blue-400 font-mono">
                {graphData.edges.length} connections
              </p>
            </div>

            <div className="glass-card rounded-2xl p-6 border border-primary/20 shadow-xl">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-2 rounded-lg bg-amber-500/20">
                  <Zap className="h-5 w-5 text-amber-400" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground font-mono">
                    AI Insights
                  </p>
                  <p className="text-2xl font-bold font-mono text-foreground">
                    342
                  </p>
                </div>
              </div>
              <p className="text-xs text-amber-400 font-mono">
                Generated this week
              </p>
            </div>
          </motion.div>

          {/* Bottom Glow Divider */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.2 }}
            className="mt-8 h-[1px] bg-gradient-to-r from-transparent via-primary/40 to-transparent shadow-[0_0_15px_rgba(147,197,253,0.4)]"
          />
        </motion.div>
      </div>
    </div>
  );
}
