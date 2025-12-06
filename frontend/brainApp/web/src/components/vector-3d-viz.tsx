"use client";

import { useEffect, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Text, Line } from "@react-three/drei";
import { motion, AnimatePresence } from "framer-motion";
import * as THREE from "three";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface VectorNode {
  coords3d: [number, number, number];
  subject?: string;
  brief_caption?: string;
  summary?: string;
  community_id?: string;
  clip_id?: string;
}

interface Vector3DVizProps {
  communities: VectorNode[];
  cards: VectorNode[];
  answer: string;
  onAnimationComplete?: () => void;
}

const MARKDOWN_STYLES = [
  // Base text styles
  'text-base text-white/95 leading-loose',
  // List styles
  '[&_ol]:pl-6 [&_ul]:pl-6',
  '[&_li]:ml-4 [&_li]:mb-2 [&_li]:leading-loose',
  // Text formatting
  '[&_strong]:font-bold [&_strong]:text-white',
  '[&_em]:italic [&_em]:text-white/90',
  // Heading styles - H1 (largest)
  '[&_h1]:text-3xl [&_h1]:font-extrabold [&_h1]:my-6 [&_h1]:text-white [&_h1]:tracking-tight [&_h1]:font-mono [&_h1]:leading-relaxed',
  // H2
  '[&_h2]:text-2xl [&_h2]:font-extrabold [&_h2]:my-6 [&_h2]:text-white [&_h2]:tracking-tight [&_h2]:font-mono [&_h2]:leading-relaxed',
  // H3
  '[&_h3]:text-xl [&_h3]:font-bold [&_h3]:my-6 [&_h3]:text-white [&_h3]:tracking-tight [&_h3]:font-mono [&_h3]:leading-relaxed',
  // H4
  '[&_h4]:text-lg [&_h4]:font-bold [&_h4]:my-3 [&_h4]:text-white [&_h4]:leading-relaxed',
  // Paragraphs
  '[&_p]:my-2 [&_p]:leading-normal',
  // Code
  '[&_code]:bg-blue-500/15 [&_code]:text-blue-400 [&_code]:px-2 [&_code]:py-1 [&_code]:rounded [&_code]:text-sm [&_code]:font-mono',
].join(' ');

function AnimatedVectorPoint({
  position,
  label,
  color,
  delay,
}: {
  position: [number, number, number];
  label: string;
  color: string;
  delay: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const lineRef = useRef<THREE.Group>(null);
  const [lineProgress, setLineProgress] = useState(0);
  const [showSphere, setShowSphere] = useState(false);
  const [showLabel, setShowLabel] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      // Animate line over 2000ms (much slower)
      const lineAnimStart = Date.now();
      const lineAnimDuration = 2000;
      
      const animateLine = () => {
        const elapsed = Date.now() - lineAnimStart;
        const progress = Math.min(elapsed / lineAnimDuration, 1);
        setLineProgress(progress);
        
        if (progress < 1) {
          requestAnimationFrame(animateLine);
        } else {
          setShowSphere(true);
          setTimeout(() => setShowLabel(true), 400);
        }
      };
      animateLine();
    }, delay);
    return () => clearTimeout(timer);
  }, [delay]);

  // No animation on sphere size

  // Calculate the current end point of the line based on progress
  const currentEnd: [number, number, number] = [
    position[0] * lineProgress,
    position[1] * lineProgress,
    position[2] * lineProgress,
  ];

  return (
    <group>
      {/* Animated Vector line from origin with arrow */}
      {lineProgress > 0 && (
        <group ref={lineRef}>
          <Line
            points={[
              [0, 0, 0],
              currentEnd,
            ]}
            color={color}
            lineWidth={2}
            transparent
          />
          
          {/* Arrow head at the end of line */}
          {lineProgress > 0.1 && (
            <mesh position={currentEnd}>
              <coneGeometry args={[0.03, 0.1, 8]} />
              <meshStandardMaterial
                color={color}
                emissive={color}
                emissiveIntensity={0.8}
              />
            </mesh>
          )}
        </group>
      )}

      {/* Point sphere - extremely small */}
      {showSphere && (
        <group position={position}>
          <mesh ref={meshRef} scale={0.0008}>
            <sphereGeometry args={[1, 16, 16]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={1.5}
              metalness={0.9}
              roughness={0.1}
            />
          </mesh>

          {/* Subtle glow effect */}
          <mesh scale={0.0016}>
            <sphereGeometry args={[1, 8, 8]} />
            <meshBasicMaterial
              color={color}
              transparent
              opacity={0.5}
              side={THREE.BackSide}
            />
          </mesh>
        </group>
      )}

      {/* Label */}
      {showLabel && (
        <Text
          position={[position[0], position[1] + 0.15, position[2]]}
          fontSize={0.08}
          color="white"
          anchorX="center"
          anchorY="middle"
          outlineWidth={0.01}
          outlineColor="#000000"
        >
          {label}
        </Text>
      )}
    </group>
  );
}

function Scene({ communities, cards }: { communities: VectorNode[]; cards: VectorNode[] }) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.1) * 0.2;
    }
  });

  return (
    <group ref={groupRef}>
      {/* Ambient lighting */}
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      <pointLight position={[-10, -10, -10]} intensity={0.5} color="#4169E1" />

      {/* Communities (purple/pink) */}
      {communities.map((comm, idx) => {
        if (!comm.coords3d) return null;
        const label = comm.summary?.slice(0, 30) || `Community ${idx + 1}`;
        return (
          <AnimatedVectorPoint
            key={`comm-${comm.community_id || idx}`}
            position={comm.coords3d}
            label={label}
            color="#A78BFA"
            delay={idx * 800}
          />
        );
      })}

      {/* Cards (cyan/blue) */}
      {cards.map((card, idx) => {
        if (!card.coords3d) return null;
        const label = card.subject || card.brief_caption?.slice(0, 30) || `Card ${idx + 1}`;
        return (
          <AnimatedVectorPoint
            key={`card-${card.clip_id || idx}`}
            position={card.coords3d}
            label={label}
            color="#60A5FA"
            delay={(communities.length + idx) * 800}
          />
        );
      })}

      {/* Origin sphere */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[0.05, 16, 16]} />
        <meshStandardMaterial
          color="#ffffff"
          emissive="#ffffff"
          emissiveIntensity={0.5}
        />
      </mesh>

      {/* Grid helper */}
      <gridHelper args={[10, 10, "#333333", "#222222"]} />
    </group>
  );
}

export function Vector3DViz({ communities, cards, answer, onAnimationComplete }: Vector3DVizProps) {
  const [showAnswer, setShowAnswer] = useState(false);
  const totalNodes = communities.length + cards.length;
  // Each node has 800ms delay, plus 2000ms line animation, plus 400ms sphere/label, plus 800ms buffer
  const animationDuration = totalNodes * 800 + 2000 + 400 + 800;

  useEffect(() => {
    const timer = setTimeout(() => {
      setShowAnswer(true);
      onAnimationComplete?.();
    }, animationDuration);
    return () => clearTimeout(timer);
  }, [animationDuration, onAnimationComplete]);

  return (
    <div className="flex flex-col h-full w-full">
      <AnimatePresence mode="wait">
        {!showAnswer ? (
          <motion.div
            key="canvas"
            className="relative flex-1 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.5 }}
          >
            <Canvas
              camera={{ position: [3, 3, 5], fov: 50 }}
              gl={{ antialias: true }}
              style={{ background: "transparent" }}
            >
              <Scene communities={communities} cards={cards} />
              <OrbitControls
                enablePan={true}
                enableZoom={true}
                enableRotate={true}
                autoRotate={true}
                autoRotateSpeed={0.5}
              />
            </Canvas>

            {/* Legend */}
            <div className="absolute top-4 right-4 bg-black/60 backdrop-blur-sm rounded-lg p-4 border border-white/10">
              <div className="text-xs font-mono text-white/90 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-purple-400"></div>
                  <span>Communities ({communities.length})</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-400"></div>
                  <span>Cards ({cards.length})</span>
                </div>
              </div>
            </div>

            {/* Animation Progress */}
            <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 bg-black/60 backdrop-blur-sm rounded-full px-6 py-3 border border-white/10">
              <div className="text-xs font-mono text-white/90 flex items-center gap-2">
                <motion.div
                  className="w-2 h-2 rounded-full bg-blue-400"
                  animate={{ scale: [1, 1.5, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                Mapping knowledge vectors...
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="answer"
            className="flex-1 min-h-0 overflow-y-auto custom-scrollbar"
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1] }}
          >
            <div className="p-8 pb-32 max-w-4xl mx-auto">
              <motion.div
                initial={{ y: 30, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.3, duration: 0.5 }}
              >
                
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5, duration: 0.6 }}
                  className={MARKDOWN_STYLES}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {answer}
                  </ReactMarkdown>
                </motion.div>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
