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
                Encrypted local screenshot memory with source-grounded retrieval.
                Remote processing is off by default.
              </p>
              <a
                href="http://127.0.0.1:8000/privacy"
                className="mt-4 inline-flex rounded-md border border-primary/50 px-4 py-2 font-mono text-sm text-foreground outline-none hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-primary"
              >
                Review privacy status
              </a>
            </div>

            {/* Knowledge Graph */}
            <div className="w-full flex-shrink">
              <p className="mb-2 text-xs font-mono text-muted-foreground">
                Prototype visualization — not a view of stored private memories.
              </p>
              <KnowledgeGraph nodes={graphData.nodes} edges={graphData.edges} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
