"use client"

import { Navbar } from "@/components/navbar"
import { AnimatedBackground } from "@/components/animated-background"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { TrendingUp, Sparkles, Target } from "lucide-react"

// Mock data for consumption over time
const consumptionData = [
  { date: "Mon", succs: 12 },
  { date: "Tue", succs: 19 },
  { date: "Wed", succs: 15 },
  { date: "Thu", succs: 25 },
  { date: "Fri", succs: 22 },
  { date: "Sat", succs: 30 },
  { date: "Sun", succs: 28 },
]

// Mock data for content categorization
const categoryData = [
  { name: "Educational", value: 65, color: "#10b981" },
  { name: "Brain Rot", value: 35, color: "#f59e0b" },
]

export default function DashboardPage() {
  return (
    <div className="flex min-h-screen flex-col animated-gradient relative overflow-hidden">
      <div className="terminal-grid" />
      <div className="scan-line" />

      <AnimatedBackground />

      <Navbar />

      <main className="flex-1 p-6 lg:p-8 relative z-10 pt-24">
        <div className="mx-auto max-w-7xl space-y-8">
          {/* Header */}
          <div className="space-y-2 animate-in fade-in duration-700">
            <h1 className="font-mono text-3xl font-semibold tracking-tight text-white">Dashboard</h1>
            <p className="font-mono text-sm text-zinc-500">Your personal intelligence system analytics</p>
          </div>

          {/* AI-Generated Insights */}
          <Card className="border-zinc-800 bg-zinc-950/50 transition-all duration-300 hover:bg-zinc-950/70 hover:border-blue-500/40 hover:shadow-lg hover:shadow-blue-500/20 animate-in slide-in-from-bottom-4 duration-700 delay-150">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-blue-400 animate-pulse" />
                <CardTitle className="font-mono text-white">AI-Generated Insights</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-lg border border-zinc-800 bg-black/50 p-4 transition-all duration-200 hover:border-blue-500/40 hover:bg-black/70">
                <p className="font-mono text-sm text-zinc-300">
                  "You've engaged most with <span className="text-blue-400">science</span> and{" "}
                  <span className="text-blue-400">humor</span> this week."
                </p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-black/50 p-4 transition-all duration-200 hover:border-blue-500/40 hover:bg-black/70">
                <p className="font-mono text-sm text-zinc-300">
                  "Recurring concepts: <span className="text-blue-400">exploration</span>,{" "}
                  <span className="text-blue-400">creativity</span>,{" "}
                  <span className="text-blue-400">human behavior</span>."
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Top Row - Consumption & Categorization */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Consumption Overview */}
            <Card className="border-zinc-800 bg-zinc-950/50 transition-all duration-300 hover:bg-zinc-950/70 hover:border-blue-500/40 hover:shadow-lg hover:shadow-blue-500/20 animate-in slide-in-from-left-8 duration-700 delay-300">
              <CardHeader>
                <CardTitle className="font-mono text-white">Consumption Overview</CardTitle>
                <CardDescription className="font-mono text-zinc-500">Knowledge growth over time</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Line Chart */}
                <div className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={consumptionData}>
                      <defs>
                        <linearGradient id="colorSuccs" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" stroke="#52525b" style={{ fontSize: "12px", fontFamily: "monospace" }} />
                      <YAxis stroke="#52525b" style={{ fontSize: "12px", fontFamily: "monospace" }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#09090b",
                          border: "1px solid #27272a",
                          borderRadius: "6px",
                          fontFamily: "monospace",
                        }}
                      />
                      <Area type="monotone" dataKey="succs" stroke="#60a5fa" fillOpacity={1} fill="url(#colorSuccs)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* Key Metrics */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-1 transition-all duration-200 hover:scale-105">
                    <p className="font-mono text-xs text-zinc-500">Total SUCCs</p>
                    <p className="font-mono text-2xl font-semibold text-white">151</p>
                  </div>
                  <div className="space-y-1 transition-all duration-200 hover:scale-105">
                    <p className="font-mono text-xs text-zinc-500">Daily Avg</p>
                    <p className="font-mono text-2xl font-semibold text-white">21.6</p>
                  </div>
                  <div className="space-y-1 transition-all duration-200 hover:scale-105">
                    <p className="font-mono text-xs text-zinc-500">Longest Streak</p>
                    <p className="font-mono text-2xl font-semibold text-white">14d</p>
                  </div>
                </div>

                {/* Trend Indicator */}
                <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-black/50 p-3 transition-all duration-200 hover:border-blue-500/50 hover:bg-black/70">
                  <TrendingUp className="h-4 w-4 text-blue-400" />
                  <span className="font-mono text-sm text-zinc-300">
                    <span className="text-blue-400">+23%</span> from last week
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Content Categorization */}
            <Card className="border-zinc-800 bg-zinc-950/50 transition-all duration-300 hover:bg-zinc-950/70 hover:border-blue-500/40 hover:shadow-lg hover:shadow-blue-500/20 animate-in slide-in-from-right-8 duration-700 delay-300">
              <CardHeader>
                <CardTitle className="font-mono text-white">Content Focus</CardTitle>
                <CardDescription className="font-mono text-zinc-500">Categorization breakdown</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Bar Chart */}
                <div className="h-[200px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={categoryData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="name" stroke="#52525b" style={{ fontSize: "12px", fontFamily: "monospace" }} />
                      <YAxis stroke="#52525b" style={{ fontSize: "12px", fontFamily: "monospace" }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#09090b",
                          border: "1px solid #27272a",
                          borderRadius: "6px",
                          fontFamily: "monospace",
                        }}
                      />
                      <Bar dataKey="value" fill="#60a5fa" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Category Breakdown */}
                <div className="grid gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm text-zinc-300">Educational SUCCs</span>
                      <span className="font-mono text-sm font-semibold text-blue-400">65%</span>
                    </div>
                    <div className="space-y-1">
                      <p className="font-mono text-xs text-zinc-500">Top Topics:</p>
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-md bg-blue-400/10 px-2 py-1 font-mono text-xs text-blue-400 transition-all duration-200 hover:bg-blue-400/20 hover:scale-105">
                          Quantum Physics
                        </span>
                        <span className="rounded-md bg-blue-400/10 px-2 py-1 font-mono text-xs text-blue-400 transition-all duration-200 hover:bg-blue-400/20 hover:scale-105">
                          AI Ethics
                        </span>
                        <span className="rounded-md bg-blue-400/10 px-2 py-1 font-mono text-xs text-blue-400 transition-all duration-200 hover:bg-blue-400/20 hover:scale-105">
                          Sourdough
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm text-zinc-300">Brain Rot SUCCs</span>
                      <span className="font-mono text-sm font-semibold text-orange-400">35%</span>
                    </div>
                    <div className="space-y-1">
                      <p className="font-mono text-xs text-zinc-500">Top Themes:</p>
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-md bg-orange-400/10 px-2 py-1 font-mono text-xs text-orange-400 transition-all duration-200 hover:bg-orange-400/20 hover:scale-105">
                          Viral Dances
                        </span>
                        <span className="rounded-md bg-orange-400/10 px-2 py-1 font-mono text-xs text-orange-400 transition-all duration-200 hover:bg-orange-400/20 hover:scale-105">
                          Cat Videos
                        </span>
                        <span className="rounded-md bg-orange-400/10 px-2 py-1 font-mono text-xs text-orange-400 transition-all duration-200 hover:bg-orange-400/20 hover:scale-105">
                          Satisfying Loops
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Engagement Tracker */}
          <Card className="border-zinc-800 bg-zinc-950/50 transition-all duration-300 hover:bg-zinc-950/70 hover:border-blue-500/40 hover:shadow-lg hover:shadow-blue-500/20 animate-in slide-in-from-bottom-8 duration-700 delay-500">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Target className="h-5 w-5 text-blue-400" />
                <CardTitle className="font-mono text-white">Engagement Tracker</CardTitle>
              </div>
              <CardDescription className="font-mono text-zinc-500">
                Progress on content processing and analysis
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-6 md:grid-cols-3">
                {/* Videos Summarized */}
                <div className="space-y-3 transition-all duration-200 hover:scale-105">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm text-zinc-300">Videos Summarized</span>
                    <span className="font-mono text-sm font-semibold text-blue-400">78%</span>
                  </div>
                  <Progress value={78} className="h-2" />
                  <p className="font-mono text-xs text-zinc-500">118 of 151 videos</p>
                </div>

                {/* Content Categorized */}
                <div className="space-y-3 transition-all duration-200 hover:scale-105">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm text-zinc-300">Content Categorized</span>
                    <span className="font-mono text-sm font-semibold text-blue-400">92%</span>
                  </div>
                  <Progress value={92} className="h-2" />
                  <p className="font-mono text-xs text-zinc-500">139 of 151 videos</p>
                </div>

                {/* Content Revisited */}
                <div className="space-y-3 transition-all duration-200 hover:scale-105">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm text-zinc-300">Content Revisited</span>
                    <span className="font-mono text-sm font-semibold text-blue-400">45%</span>
                  </div>
                  <Progress value={45} className="h-2" />
                  <p className="font-mono text-xs text-zinc-500">68 of 151 videos</p>
                </div>
              </div>

              {/* Weekly Activity */}
              <div className="space-y-3">
                <h3 className="font-mono text-sm font-semibold text-white">Weekly Activity</h3>
                <div className="h-[120px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={consumptionData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" stroke="#52525b" style={{ fontSize: "11px", fontFamily: "monospace" }} />
                      <YAxis stroke="#52525b" style={{ fontSize: "11px", fontFamily: "monospace" }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#09090b",
                          border: "1px solid #27272a",
                          borderRadius: "6px",
                          fontFamily: "monospace",
                        }}
                      />
                      <Line
                        type="monotone"
                        dataKey="succs"
                        stroke="#60a5fa"
                        strokeWidth={2}
                        dot={{ fill: "#60a5fa" }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
