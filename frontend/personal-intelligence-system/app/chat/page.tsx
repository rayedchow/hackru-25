import { Navbar } from "@/components/navbar"
import { ChatInterface } from "@/components/chat-interface"
import { VideoPlayer } from "@/components/video-player"
import { AnimatedBackground } from "@/components/animated-background"
import { Brain, Lightbulb, Target } from "lucide-react"

export default function ChatPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AnimatedBackground />

      <div className="absolute inset-0 bg-background/40 backdrop-blur-xl" />

      <div className="relative z-10 flex h-screen flex-col">
        <Navbar />

        <div className="flex flex-1 overflow-hidden gap-4 p-4">
          {/* Left Panel - Chat Interface */}
          <div className="flex w-2/3 flex-col rounded-2xl border border-border/50 bg-background/60 backdrop-blur-md shadow-xl overflow-hidden">
            <ChatInterface />
          </div>

          <div className="flex w-1/3 flex-col gap-4">
            {/* Context Panel */}
            <div className="flex flex-col rounded-2xl border border-border/50 bg-gradient-to-br from-background/70 to-background/50 backdrop-blur-md shadow-xl p-6 gap-4">
              <h2 className="text-sm font-mono font-semibold text-foreground/80 flex items-center gap-2">
                <Brain className="h-4 w-4 text-primary" />
                AI Context
              </h2>

              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 rounded-lg bg-background/40 border border-border/30">
                  <Target className="h-4 w-4 text-primary mt-0.5" />
                  <div>
                    <div className="text-xs font-mono font-medium text-foreground/70">Current Task</div>
                    <div className="text-xs text-muted-foreground mt-1">Project Planning & Setup</div>
                  </div>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-lg bg-background/40 border border-border/30">
                  <Lightbulb className="h-4 w-4 text-yellow-500 mt-0.5" />
                  <div>
                    <div className="text-xs font-mono font-medium text-foreground/70">Last Topic</div>
                    <div className="text-xs text-muted-foreground mt-1">Personal intelligence system architecture</div>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-border/30">
                <div className="text-xs font-mono font-medium text-foreground/70 mb-2">Active Concepts</div>
                <div className="flex flex-wrap gap-2">
                  {["Learning", "Explore", "Karma"].map((concept) => (
                    <span
                      key={concept}
                      className="px-2 py-1 rounded-md bg-primary/20 border border-primary/30 text-xs font-mono text-primary"
                    >
                      {concept}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Video Player */}
            <div className="flex flex-1 rounded-2xl border border-border/50 bg-background/60 backdrop-blur-md shadow-xl overflow-hidden">
              <VideoPlayer />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
