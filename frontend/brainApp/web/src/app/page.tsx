import { Navbar } from "@/components/navbar";
import { AnimatedBackground } from "@/components/animated-background";
import { Brain, Camera, Sparkles, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AnimatedBackground />

      <div className="absolute inset-0 bg-background/40 backdrop-blur-xl" />

      <div className="relative z-10 flex h-screen flex-col">
        <Navbar />

        <div className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-4xl w-full text-center">
            {/* Hero Section */}
            <div className="space-y-8">
              <div className="space-y-4">
                <h1 className="text-6xl font-bold font-mono text-foreground terminal-glow">
                  Brain App
                </h1>
                <p className="text-xl text-muted-foreground font-mono max-w-2xl mx-auto">
                  Personal intelligence system with instant screenshot capture
                  and AI-powered analysis
                </p>
              </div>

              {/* Features */}
              <div className="grid md:grid-cols-3 gap-6 mt-12">
                <div className="glass-card rounded-2xl p-6 space-y-4">
                  <Camera className="h-12 w-12 text-primary mx-auto" />
                  <h3 className="text-lg font-mono font-semibold text-foreground">
                    Instant Capture
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Press Command + J to capture any region of your screen
                    instantly
                  </p>
                </div>

                <div className="glass-card rounded-2xl p-6 space-y-4">
                  <Brain className="h-12 w-12 text-primary mx-auto" />
                  <h3 className="text-lg font-mono font-semibold text-foreground">
                    AI Analysis
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Chat with AI about your captured content and get intelligent
                    insights
                  </p>
                </div>

                <div className="glass-card rounded-2xl p-6 space-y-4">
                  <Sparkles className="h-12 w-12 text-primary mx-auto" />
                  <h3 className="text-lg font-mono font-semibold text-foreground">
                    Smart Interface
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Beautiful, modern UI with glass morphism and smooth
                    animations
                  </p>
                </div>
              </div>

              {/* CTA */}
              <div className="space-y-4 mt-12">
                <Link
                  href="/chat"
                  className="inline-flex items-center gap-2 px-8 py-4 rounded-2xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground font-mono font-semibold transition-all duration-300 hover:scale-105 glow-primary"
                >
                  Start Capturing
                  <ArrowRight className="h-5 w-5" />
                </Link>
                <p className="text-sm text-muted-foreground font-mono">
                  Make sure the Python screenshot app is running
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
