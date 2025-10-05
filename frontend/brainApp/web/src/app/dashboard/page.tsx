import { Navbar } from "@/components/navbar";
import { AnimatedBackground } from "@/components/animated-background";
import { ScreenshotViewer } from "@/components/screenshot-viewer";
import {
  Brain,
  Camera,
  Clock,
  TrendingUp,
  Activity,
  BarChart3,
  Settings,
} from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AnimatedBackground />

      <div className="absolute inset-0 bg-background/40 backdrop-blur-xl" />

      <div className="relative z-10 flex h-screen flex-col">
        <Navbar />

        <div className="flex flex-1 overflow-hidden gap-4 p-4">
          {/* Main Dashboard Grid */}
          <div className="flex flex-1 flex-col gap-4">
            {/* Stats Row */}
            <div className="grid grid-cols-4 gap-4">
              <div className="glass-card rounded-2xl p-6 space-y-2">
                <div className="flex items-center gap-2">
                  <Camera className="h-5 w-5 text-primary" />
                  <span className="text-sm font-mono text-muted-foreground">
                    Screenshots
                  </span>
                </div>
                <div className="text-2xl font-bold font-mono text-foreground">
                  127
                </div>
                <div className="text-xs text-green-500 font-mono">
                  +12 this week
                </div>
              </div>

              <div className="glass-card rounded-2xl p-6 space-y-2">
                <div className="flex items-center gap-2">
                  <Brain className="h-5 w-5 text-primary" />
                  <span className="text-sm font-mono text-muted-foreground">
                    AI Sessions
                  </span>
                </div>
                <div className="text-2xl font-bold font-mono text-foreground">
                  43
                </div>
                <div className="text-xs text-blue-500 font-mono">
                  +8 this week
                </div>
              </div>

              <div className="glass-card rounded-2xl p-6 space-y-2">
                <div className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-primary" />
                  <span className="text-sm font-mono text-muted-foreground">
                    Time Saved
                  </span>
                </div>
                <div className="text-2xl font-bold font-mono text-foreground">
                  2.4h
                </div>
                <div className="text-xs text-purple-500 font-mono">Today</div>
              </div>

              <div className="glass-card rounded-2xl p-6 space-y-2">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-primary" />
                  <span className="text-sm font-mono text-muted-foreground">
                    Efficiency
                  </span>
                </div>
                <div className="text-2xl font-bold font-mono text-foreground">
                  94%
                </div>
                <div className="text-xs text-green-500 font-mono">
                  +3% this week
                </div>
              </div>
            </div>

            {/* Charts and Activity */}
            <div className="grid grid-cols-2 gap-4 flex-1">
              <div className="glass-card rounded-2xl p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-primary" />
                  <h3 className="text-lg font-mono font-semibold text-foreground">
                    Activity Overview
                  </h3>
                </div>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-mono text-muted-foreground">
                      Screenshots
                    </span>
                    <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full"
                        style={{ width: "75%" }}
                      ></div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-mono text-muted-foreground">
                      AI Chats
                    </span>
                    <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-secondary rounded-full"
                        style={{ width: "60%" }}
                      ></div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-mono text-muted-foreground">
                      Analysis
                    </span>
                    <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent rounded-full"
                        style={{ width: "85%" }}
                      ></div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="glass-card rounded-2xl p-6 space-y-4">
                <div className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-primary" />
                  <h3 className="text-lg font-mono font-semibold text-foreground">
                    Recent Activity
                  </h3>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-2 rounded-lg bg-background/40">
                    <Camera className="h-4 w-4 text-primary" />
                    <div className="flex-1">
                      <div className="text-sm font-mono text-foreground">
                        Screenshot captured
                      </div>
                      <div className="text-xs text-muted-foreground">
                        2 minutes ago
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-2 rounded-lg bg-background/40">
                    <Brain className="h-4 w-4 text-primary" />
                    <div className="flex-1">
                      <div className="text-sm font-mono text-foreground">
                        AI analysis completed
                      </div>
                      <div className="text-xs text-muted-foreground">
                        5 minutes ago
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-2 rounded-lg bg-background/40">
                    <Settings className="h-4 w-4 text-primary" />
                    <div className="flex-1">
                      <div className="text-sm font-mono text-foreground">
                        Settings updated
                      </div>
                      <div className="text-xs text-muted-foreground">
                        1 hour ago
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Panel - Screenshot Viewer */}
          <div className="w-1/3">
            <div className="h-full rounded-2xl border border-border/50 bg-background/60 backdrop-blur-md shadow-xl overflow-hidden">
              <ScreenshotViewer />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
