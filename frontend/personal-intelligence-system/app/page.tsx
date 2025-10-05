"use client"

import { Navbar } from "@/components/navbar"
import { KnowledgeGraph } from "@/components/knowledge-graph"
import { AnimatedBackground } from "@/components/animated-background"
import { Sparkles, Plus, Shuffle, Clock, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useState } from "react"
import { motion } from "framer-motion"

export default function Home() {
  const [inputValue, setInputValue] = useState("")

  return (
    <div className="flex h-screen flex-col animated-gradient relative overflow-hidden">
      <div className="terminal-grid" />
      <div className="scan-line" />

      <AnimatedBackground />

      <Navbar />

      <main className="flex flex-col items-center justify-center flex-1 relative z-10 px-6 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="flex flex-col items-center gap-4"
        >
          <motion.h1
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="flex items-center gap-4 text-5xl font-bold tracking-tight"
          >
            <Sparkles className="h-10 w-10 text-primary drop-shadow-[0_0_20px_rgba(147,197,253,0.8)] terminal-glow" />
            <span className="code-accent">Snehnshn returns!</span>
          </motion.h1>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.6 }}
          className="w-full max-w-2xl"
        >
          <KnowledgeGraph />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.8 }}
          className="flex flex-col items-center w-full max-w-3xl gap-4"
        >
          <motion.div
            whileHover={{ scale: 1.02 }}
            transition={{ duration: 0.2 }}
            className="w-full rounded-2xl glass-card p-1 shadow-2xl glow-primary"
          >
            <div className="flex flex-col gap-3 p-5">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="How can I help you today?"
                className="min-h-[80px] w-full resize-none bg-transparent text-base text-foreground placeholder:text-muted-foreground focus:outline-none transition-all duration-200"
              />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}>
                    <Button size="icon" variant="ghost" className="h-9 w-9 hover:bg-primary/20 hover:text-primary">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </motion.div>
                  <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}>
                    <Button size="icon" variant="ghost" className="h-9 w-9 hover:bg-primary/20 hover:text-primary">
                      <Shuffle className="h-4 w-4" />
                    </Button>
                  </motion.div>
                  <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}>
                    <Button size="icon" variant="ghost" className="h-9 w-9 hover:bg-primary/20 hover:text-primary">
                      <Clock className="h-4 w-4" />
                    </Button>
                  </motion.div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    className="h-9 text-sm text-muted-foreground hover:text-foreground hover:bg-muted"
                  >
                    Sonnet 4.5
                  </Button>
                  <motion.div whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}>
                    <Button
                      size="icon"
                      className="h-9 w-9 rounded-lg bg-gradient-to-r from-primary to-accent hover:from-accent hover:to-secondary shadow-lg glow-primary"
                    >
                      <Upload className="h-4 w-4" />
                    </Button>
                  </motion.div>
                </div>
              </div>
            </div>
          </motion.div>

          <div className="flex flex-wrap items-center justify-center gap-2">
            {["Write", "Learn", "Code", "Life stuff", "Claude's choice"].map((suggestion, index) => (
              <motion.div
                key={suggestion}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 1 + index * 0.1 }}
                whileHover={{ scale: 1.05, y: -2 }}
                whileTap={{ scale: 0.95 }}
              >
                <Button
                  variant="outline"
                  className="rounded-full glass-card text-sm text-foreground hover:bg-primary/20 hover:text-primary hover:border-primary/50 transition-all duration-300 bg-transparent"
                >
                  {suggestion}
                </Button>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </main>
    </div>
  )
}
