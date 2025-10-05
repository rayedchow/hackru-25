"use client"

import type React from "react"
import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"

interface Node {
  id: string
  label: string
  x: number
  y: number
}

interface Edge {
  from: string
  to: string
}

export function KnowledgeGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  const nodes: Node[] = [
    { id: "human", label: "Human", x: 400, y: 150 },
    { id: "karma", label: "Karma", x: 250, y: 200 },
    { id: "explore", label: "Explore", x: 350, y: 250 },
    { id: "contacts", label: "Contacts", x: 450, y: 250 },
    { id: "domains", label: "Domains", x: 550, y: 250 },
    { id: "guidelines", label: "Guidelines", x: 300, y: 320 },
    { id: "learning", label: "Learning", x: 450, y: 320 },
    { id: "notebook", label: "Notebook", x: 350, y: 380 },
    { id: "machines", label: "Machines", x: 550, y: 380 },
  ]

  const edges: Edge[] = [
    { from: "human", to: "karma" },
    { from: "human", to: "explore" },
    { from: "human", to: "contacts" },
    { from: "human", to: "domains" },
    { from: "karma", to: "guidelines" },
    { from: "explore", to: "guidelines" },
    { from: "explore", to: "notebook" },
    { from: "contacts", to: "learning" },
    { from: "domains", to: "learning" },
    { from: "domains", to: "machines" },
    { from: "learning", to: "notebook" },
  ]

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr

    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, rect.width, rect.height)

    edges.forEach((edge) => {
      const fromNode = nodes.find((n) => n.id === edge.from)
      const toNode = nodes.find((n) => n.id === edge.to)
      if (fromNode && toNode) {
        const gradient = ctx.createLinearGradient(fromNode.x, fromNode.y, toNode.x, toNode.y)
        gradient.addColorStop(0, "rgba(147, 197, 253, 0.3)")
        gradient.addColorStop(1, "rgba(196, 181, 253, 0.3)")

        ctx.strokeStyle = gradient
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(fromNode.x, fromNode.y)
        ctx.lineTo(toNode.x, toNode.y)
        ctx.stroke()
      }
    })

    nodes.forEach((node) => {
      const isHovered = hoveredNode === node.id

      if (isHovered) {
        ctx.shadowColor = "rgba(147, 197, 253, 0.8)"
        ctx.shadowBlur = 25
      }

      // Node background with gradient
      const gradient = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, 50)
      gradient.addColorStop(0, isHovered ? "rgba(147, 197, 253, 0.3)" : "rgba(147, 197, 253, 0.15)")
      gradient.addColorStop(1, "rgba(147, 197, 253, 0)")

      ctx.fillStyle = gradient
      ctx.beginPath()
      ctx.arc(node.x, node.y, 50, 0, Math.PI * 2)
      ctx.fill()

      // Node card
      ctx.fillStyle = isHovered ? "rgba(30, 41, 59, 0.9)" : "rgba(30, 41, 59, 0.7)"
      ctx.strokeStyle = isHovered ? "rgba(147, 197, 253, 1)" : "rgba(147, 197, 253, 0.5)"
      ctx.lineWidth = isHovered ? 2.5 : 1.5

      const padding = 14
      const textWidth = ctx.measureText(node.label).width
      const nodeWidth = textWidth + padding * 2
      const nodeHeight = 32

      ctx.beginPath()
      ctx.roundRect(node.x - nodeWidth / 2, node.y - nodeHeight / 2, nodeWidth, nodeHeight, 8)
      ctx.fill()
      ctx.stroke()

      ctx.shadowBlur = 0

      ctx.fillStyle = isHovered ? "rgba(147, 197, 253, 1)" : "rgba(147, 197, 253, 0.8)"
      ctx.beginPath()
      ctx.arc(node.x - nodeWidth / 2 + 18, node.y, isHovered ? 4.5 : 3.5, 0, Math.PI * 2)
      ctx.fill()

      // Node text
      ctx.fillStyle = isHovered ? "rgba(255, 255, 255, 1)" : "rgba(255, 255, 255, 0.9)"
      ctx.font = `${isHovered ? "14px" : "13px"} 'Geist Mono', monospace`
      ctx.textAlign = "center"
      ctx.textBaseline = "middle"
      ctx.fillText(node.label, node.x, node.y)
    })
  }, [hoveredNode])

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    let foundNode: string | null = null
    for (const node of nodes) {
      const padding = 14
      const ctx = canvas.getContext("2d")
      if (!ctx) continue
      const textWidth = ctx.measureText(node.label).width
      const nodeWidth = textWidth + padding * 2
      const nodeHeight = 32

      if (
        x >= node.x - nodeWidth / 2 &&
        x <= node.x + nodeWidth / 2 &&
        y >= node.y - nodeHeight / 2 &&
        y <= node.y + nodeHeight / 2
      ) {
        foundNode = node.id
        break
      }
    }

    setHoveredNode(foundNode)
    canvas.style.cursor = foundNode ? "pointer" : "default"
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6 }}
      whileHover={{ scale: 1.02 }}
      className="flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl glass-card shadow-2xl glow-primary"
    >
      <div className="relative h-[450px]">
        <canvas
          ref={canvasRef}
          className="h-full w-full"
          style={{ width: "100%", height: "100%" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredNode(null)}
        />
      </div>
    </motion.div>
  )
}
