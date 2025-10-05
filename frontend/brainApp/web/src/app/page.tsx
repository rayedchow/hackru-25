"use client";

import { Navbar } from "@/components/navbar";
import { AnimatedBackground } from "@/components/animated-background";
import { KnowledgeGraph } from "@/components/knowledge-graph";
import graphData from "@/a.json";

export default function LandingPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AnimatedBackground />

      <div className="absolute inset-0 bg-background/40 backdrop-blur-xl" />

      <div className="relative z-10 flex flex-col h-full">
        <Navbar />

        <div className="flex flex-1 items-center justify-center p-6 pt-0 overflow-hidden">
          <div className="max-w-5xl w-full text-center flex flex-col items-center justify-center gap-8">
            {/* Hero Section */}
            <div className="space-y-2">
              <h1 className="text-5xl font-bold font-mono text-foreground terminal-glow">
                Synapse
              </h1>
              <p className="text-lg text-muted-foreground font-mono max-w-2xl mx-auto">
                Personal intelligence system with instant screenshot capture and
                AI-powered analysis
              </p>
            </div>

            {/* Knowledge Graph */}
            <div className="w-full flex-shrink">
              <KnowledgeGraph nodes={graphData.nodes} edges={graphData.edges} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
