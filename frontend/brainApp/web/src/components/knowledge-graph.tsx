"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import * as d3 from "d3-force";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

interface GraphNode {
  data: {
    id: string;
    label: string;
    name?: string;
    [key: string]: any;
  };
}

interface GraphEdge {
  data: {
    id: string;
    source: string;
    target: string;
    type: string;
    [key: string]: any;
  };
}

interface KnowledgeGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function KnowledgeGraph({ nodes, edges }: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [nodePositions, setNodePositions] = useState<
    Map<string, { x: number; y: number }>
  >(new Map());

  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [userMoved, setUserMoved] = useState(false);

  // ---------- Colors by node type ----------
  const getNodeColor = (label: string) => {
    switch (label) {
      case "Clip":
        return "#60A5FA"; // blue
      case "Subject":
        return "#F87171"; // red
      case "Aesthetic":
        return "#FBBF24"; // yellow
      case "Trend":
        return "#A78BFA"; // purple
      case "TimeBin":
        return "#34D399"; // green
      default:
        return "#94A3B8"; // gray
    }
  };

  // ---------- 1) Normalize edges so all endpoints are real node IDs ----------
  const normalizedEdges = useMemo(() => {
    if (!nodes.length) return [] as GraphEdge[];

    const idSet = new Set(nodes.map((n) => n.data.id));
    const mapEndpoint = (v: string): string | null => {
      if (idSet.has(v)) return v; // already a real id
      // Convert array-index-like references ("0","7","12") to actual node ids
      if (/^\d+$/.test(v)) {
        const idx = parseInt(v, 10);
        if (idx >= 0 && idx < nodes.length) return nodes[idx].data.id;
      }
      return null;
    };

    const out: GraphEdge[] = [];
    for (const e of edges) {
      const s = mapEndpoint(e.data.source);
      const t = mapEndpoint(e.data.target);
      if (s && t) {
        out.push({
          ...e,
          data: { ...e.data, source: s, target: t },
        });
      }
    }
    return out;
  }, [nodes, edges]);

  // ---------- 2) Run compact force layout ----------
  useEffect(() => {
    if (!nodes.length) return;

    const canvas = canvasRef.current;
    const width = canvas?.clientWidth ?? 800;
    const height = canvas?.clientHeight ?? 400;

    const simNodes: Array<any> = nodes.map((n) => ({ id: n.data.id }));
    const simLinks = normalizedEdges.map((e) => ({
      source: e.data.source,
      target: e.data.target,
    }));

    const simulation = d3
      .forceSimulation(simNodes)
      .force(
        "link",
        d3
          .forceLink(simLinks)
          .id((d: any) => d.id)
          .distance(60) // tighter
          .strength(0.35)
      )
      .force("charge", d3.forceManyBody().strength(-120)) // not too repulsive
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(12))
      .stop();

    simulation.tick(280);

    const positions = new Map<string, { x: number; y: number }>();
    simNodes.forEach((n: any) => {
      positions.set(n.id, { x: n.x, y: n.y });
    });
    setNodePositions(positions);
    setUserMoved(false); // new layout -> allow auto-fit
  }, [nodes, normalizedEdges]);

  // ---------- 3) Auto-fit into the visible canvas (with margin) ----------
  const zoomToFit = () => {
    const canvas = canvasRef.current;
    if (!canvas || nodePositions.size === 0) return;

    const rect = canvas.getBoundingClientRect();
    const cw = rect.width;
    const ch = rect.height;
    if (!cw || !ch) return;

    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;

    nodePositions.forEach(({ x, y }) => {
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    });

    const margin = 40;
    const bboxW = Math.max(1, maxX - minX);
    const bboxH = Math.max(1, maxY - minY);

    const k = Math.min(
      5,
      Math.max(
        0.4,
        0.9 * Math.min(cw / (bboxW + margin * 2), ch / (bboxH + margin * 2))
      )
    );

    const x = cw / 2 - k * (minX + bboxW / 2);
    const y = ch / 2 - k * (minY + bboxH / 2);

    setTransform({ x, y, k });
  };

  // Fit once when positions appear/update (unless user has moved view)
  useEffect(() => {
    if (!userMoved) zoomToFit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodePositions]);

  // Re-fit if container size changes
  useEffect(() => {
    const el = canvasRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      if (!userMoved) zoomToFit();
    });
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodePositions, userMoved]);

  // ---------- 4) Draw ----------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodePositions.size === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // reset & scale for DPR

    ctx.clearRect(0, 0, width, height);

    ctx.save();
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // edges with glow
    for (const e of normalizedEdges) {
      const a = nodePositions.get(e.data.source);
      const b = nodePositions.get(e.data.target);
      if (!a || !b) continue;

      // Outer glow
      ctx.strokeStyle = "rgba(147, 197, 253, 0.2)";
      ctx.lineWidth = 3;
      ctx.shadowColor = "rgba(147, 197, 253, 0.4)";
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();

      // Inner line
      ctx.strokeStyle = "rgba(147, 197, 253, 0.5)";
      ctx.lineWidth = 1.5;
      ctx.shadowBlur = 0;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.shadowBlur = 0;

    // nodes
    for (const n of nodes) {
      const pos = nodePositions.get(n.data.id);
      if (!pos) continue;
      const isHovered = hoveredNode === n.data.id;
      const r = isHovered ? 8 : 6;
      const color = getNodeColor(n.data.label);

      // Very subtle glow outline
      ctx.shadowColor = color;
      ctx.shadowBlur = isHovered ? 8 : 4;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      ctx.shadowBlur = 0;

      if (isHovered) {
        const label = n.data.name || n.data.label;
        ctx.font = "12px 'Geist Mono', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";

        // Text shadow for readability
        ctx.shadowColor = "rgba(0, 0, 0, 0.8)";
        ctx.shadowBlur = 4;
        ctx.fillStyle = "rgba(226,232,240,0.95)";
        ctx.fillText(label, pos.x, pos.y + r + 6);
        ctx.shadowBlur = 0;
      }
    }

    ctx.restore();
  }, [nodes, nodePositions, normalizedEdges, hoveredNode, transform]);

  // ---------- 5) Interactions (hover, zoom, pan) ----------
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - transform.x) / transform.k;
    const y = (e.clientY - rect.top - transform.y) / transform.k;

    let found: string | null = null;
    for (const node of nodes) {
      const p = nodePositions.get(node.data.id);
      if (!p) continue;
      const d = Math.hypot(x - p.x, y - p.y);
      if (d < 12) {
        found = node.data.id;
        break;
      }
    }
    setHoveredNode(found);
    canvas.style.cursor = found ? "pointer" : "default";
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const scale = Math.exp(-e.deltaY * 0.001);
    setTransform((t) => {
      const k = Math.min(5, Math.max(0.4, t.k * scale));
      return { ...t, k };
    });
    setUserMoved(true);
  };

  const isDragging = useRef(false);
  const lastPos = useRef<{ x: number; y: number } | null>(null);

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    isDragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
  };
  const handleMouseUp = () => {
    isDragging.current = false;
    lastPos.current = null;
  };
  const handleMouseDrag = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDragging.current || !lastPos.current) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    setTransform((t) => ({ ...t, x: t.x + dx, y: t.y + dy }));
    lastPos.current = { x: e.clientX, y: e.clientY };
    setUserMoved(true);
  };

  // ---------- UI ----------
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-6xl mx-auto"
    >
      <div className="glass-card rounded-2xl p-6 shadow-2xl glow-primary">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-mono font-semibold text-foreground/80 flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
            Knowledge Graph
            <span className="text-xs text-muted-foreground ml-2">
              {nodes.length} nodes · {normalizedEdges.length} edges
            </span>
          </h3>

          <button
            onClick={() => {
              setUserMoved(false);
              zoomToFit();
            }}
            className="text-xs px-2 py-1 rounded-md border border-white/10 bg-white/5 hover:bg-white/10"
          >
            Fit
          </button>
        </div>

        <div className="relative h-[450px] rounded-xl overflow-hidden bg-background/20">
          <canvas
            ref={canvasRef}
            className="h-full w-full cursor-grab"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoveredNode(null)}
            onWheel={handleWheel}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            onMouseMoveCapture={handleMouseDrag}
          />

          {/* depth gradient */}
          <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-background/50 via-transparent to-background/20" />

          {/* Legend */}
          <div className="absolute bottom-4 left-4 bg-black/40 text-xs text-gray-200 p-2 rounded-lg backdrop-blur-md">
            <div className="flex flex-wrap gap-2">
              <span>
                <span className="inline-block w-3 h-3 rounded-full bg-blue-400 mr-1" />
                Clip
              </span>
              <span>
                <span className="inline-block w-3 h-3 rounded-full bg-red-400 mr-1" />
                Subject
              </span>
              <span>
                <span className="inline-block w-3 h-3 rounded-full bg-yellow-400 mr-1" />
                Aesthetic
              </span>
              <span>
                <span className="inline-block w-3 h-3 rounded-full bg-purple-400 mr-1" />
                Trend
              </span>
              <span>
                <span className="inline-block w-3 h-3 rounded-full bg-green-400 mr-1" />
                TimeBin
              </span>
            </div>
          </div>

          {/* CTA Button */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 pointer-events-auto">
            <Link
              href="/chat"
              className="inline-flex items-center gap-2 px-8 py-4 rounded-2xl bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 text-primary-foreground font-mono font-semibold transition-all duration-300 hover:scale-105 glow-primary shadow-2xl backdrop-blur-sm border border-primary/20"
            >
              Start Capturing
              <ArrowRight className="h-5 w-5" />
            </Link>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
