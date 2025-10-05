"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Play, Pause, Volume2, Maximize2, SkipForward } from "lucide-react"

export function VideoPlayer() {
  const [isPlaying, setIsPlaying] = useState(false)
  const [volume, setVolume] = useState([75])

  return (
    <div className="flex h-full w-full flex-col bg-card">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-6 py-4">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-red-500/80" />
          <div className="h-3 w-3 rounded-full bg-yellow-500/80" />
          <div className="h-3 w-3 rounded-full bg-green-500/80" />
        </div>
        <h2 className="font-mono text-sm text-muted-foreground">SOP's Title</h2>
      </div>

      {/* Video Display */}
      <div className="flex flex-1 items-center justify-center bg-background/50">
        <div className="flex h-32 w-32 items-center justify-center rounded-full bg-card/50 backdrop-blur-sm">
          <Play className="h-16 w-16 text-foreground/60" />
        </div>
      </div>

      {/* Controls */}
      <div className="space-y-4 border-t border-border p-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setIsPlaying(!isPlaying)}>
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </Button>

          <div className="flex flex-1 items-center gap-3">
            <Volume2 className="h-4 w-4 text-muted-foreground" />
            <Slider value={volume} onValueChange={setVolume} max={100} step={1} className="flex-1" />
            <span className="font-mono text-xs text-muted-foreground">{volume[0]}%</span>
          </div>

          <Button variant="ghost" size="icon" className="h-8 w-8">
            <SkipForward className="h-4 w-4" />
          </Button>

          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Maximize2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
