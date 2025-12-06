"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Send,
  Search,
  FileText,
  Save,
  Copy,
  Bookmark,
  Sparkles,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Vector3DViz } from "@/components/vector-3d-viz";

interface Message {
  id: number;
  text: string;
  sender: "user" | "bot";
  timestamp?: string;
}

interface ApiResponse {
  answer: string;
  communities: any[];
  cards: any[];
  projection: string;
}

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: "Hello! I'm ready to help you analyze screenshots and answer questions.",
      sender: "bot",
      timestamp: "2:30 PM",
    },
    {
      id: 2,
      text: "Press Command + J to capture a screenshot, then ask me about it!",
      sender: "bot",
      timestamp: "2:31 PM",
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [hoveredMessage, setHoveredMessage] = useState<number | null>(null);
  const [showViz, setShowViz] = useState(false);
  const [vizData, setVizData] = useState<ApiResponse | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [screenshotPreview, setScreenshotPreview] = useState<string | null>(null);

  const handleSend = async () => {
    if (input.trim()) {
      const userQuestion = input;
      setCurrentQuestion(userQuestion);
      setInput("");
      setIsTyping(true);
      
      try {
        // Check if there's a screenshot available
        const screenshotCheck = await fetch("/api/screenshot?t=" + Date.now());
        const screenshotData = await screenshotCheck.json();
        
        let response;
        
        if (screenshotData.url) {
          // Fetch screenshot as base64
          const base64Response = await fetch("/api/screenshot?base64=true");
          const base64Data = await base64Response.json();
          
          if (base64Data.base64) {
            // Store screenshot preview temporarily
            setScreenshotPreview(`data:image/png;base64,${base64Data.base64}`);
            
            // Call /ask_screenshot with base64 image
            response = await fetch("http://localhost:8000/ask_screenshot", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                screenshot: base64Data.base64,
              }),
            });
            
            // Delete the latest.png file
            await fetch("/api/screenshot", {
              method: "DELETE",
            });
          } else {
            throw new Error("Failed to get screenshot base64");
          }
        } else {
          // No screenshot, use regular question endpoint
          response = await fetch("http://localhost:8000/ask_question", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              question: userQuestion,
            }),
          });
        }

        const data = await response.json();
        
        setIsTyping(false);
        
        // Show 3D visualization with the results
        if (data.result) {
          setVizData(data.result);
          setShowViz(true);
        }
      } catch (error) {
        setIsTyping(false);
        alert("Sorry, I encountered an error while processing your request. Please make sure the backend server is running.");
        console.error("Error calling API:", error);
      }
    }
  };

  const handleCloseViz = () => {
    setShowViz(false);
    setVizData(null);
    setCurrentQuestion("");
    setScreenshotPreview(null);
  };

  const quickActions = [
    {
      icon: Search,
      label: "Search knowledge",
      action: () => console.log("Search"),
    },
    {
      icon: FileText,
      label: "Summarize chat",
      action: () => console.log("Summarize"),
    },
    { icon: Save, label: "Save to project", action: () => console.log("Save") },
  ];

  return (
    <div className="flex h-full flex-col">
      {/* Show 3D Visualization or Input Interface */}
      <AnimatePresence mode="wait">
        {showViz && vizData ? (
          <motion.div
            key="viz"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex flex-col relative"
          >
            {/* Header with question and close button */}
            <div className="flex items-center justify-between border-b border-border/50 bg-gradient-to-r from-background/40 to-background/20 px-6 py-4 backdrop-blur-sm">
              <div className="flex items-center gap-3 flex-1">
                <Sparkles className="h-5 w-5 text-primary" />
                <h2 className="font-mono text-sm text-foreground/90">
                  {currentQuestion}
                </h2>
              </div>
              <motion.button
                whileHover={{ scale: 1.1, rotate: 90 }}
                whileTap={{ scale: 0.9 }}
                onClick={handleCloseViz}
                className="p-2 rounded-lg bg-background/60 hover:bg-background/80 border border-border/40 text-foreground/70 hover:text-foreground transition-colors"
              >
                <X className="h-4 w-4" />
              </motion.button>
            </div>

            {/* 3D Visualization */}
            <div className="flex-1 overflow-hidden">
              <Vector3DViz
                communities={vizData.communities || []}
                cards={vizData.cards || []}
                answer={vizData.answer || ""}
              />
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="input"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border/50 bg-gradient-to-r from-background/40 to-background/20 px-6 py-4 backdrop-blur-sm">
              <div className="flex items-center gap-3">
                <motion.h1
                  className="font-mono text-sm text-foreground/70 flex items-center gap-2"
                  animate={{ opacity: isTyping ? [1, 0.5, 1] : 1 }}
                  transition={{
                    duration: 1.5,
                    repeat: isTyping ? Number.POSITIVE_INFINITY : 0,
                  }}
                >
                  {isTyping && (
                    <motion.div
                      className="flex gap-1"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                    >
                      <motion.div
                        className="h-1.5 w-1.5 rounded-full bg-primary"
                        animate={{ scale: [1, 1.5, 1] }}
                        transition={{
                          duration: 0.6,
                          repeat: Number.POSITIVE_INFINITY,
                          delay: 0,
                        }}
                      />
                      <motion.div
                        className="h-1.5 w-1.5 rounded-full bg-primary"
                        animate={{ scale: [1, 1.5, 1] }}
                        transition={{
                          duration: 0.6,
                          repeat: Number.POSITIVE_INFINITY,
                          delay: 0.2,
                        }}
                      />
                      <motion.div
                        className="h-1.5 w-1.5 rounded-full bg-primary"
                        animate={{ scale: [1, 1.5, 1] }}
                        transition={{
                          duration: 0.6,
                          repeat: Number.POSITIVE_INFINITY,
                          delay: 0.4,
                        }}
                      />
                    </motion.div>
                  )}
                </motion.h1>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="border-t border-border/30 bg-background/20 px-4 py-2 backdrop-blur-sm">
              <div className="flex gap-2 justify-center">
                {quickActions.map((action, index) => (
                  <motion.button
                    key={index}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={action.action}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-background/60 hover:bg-background/80 border border-border/40 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <action.icon className="h-3.5 w-3.5" />
                    {action.label}
                  </motion.button>
                ))}
              </div>
            </div>

            {/* Input Area */}
            <div className="border-t border-border/50 bg-gradient-to-r from-background/40 to-background/20 p-4 backdrop-blur-sm">
              <div className="flex gap-2">
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder="Ask about your screenshots or type a message..."
                  className="flex-1 bg-background/60 backdrop-blur-sm border-border/50 font-mono text-sm focus:ring-2 focus:ring-primary/50"
                  disabled={isTyping}
                />
                <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
                  <Button
                    onClick={handleSend}
                    size="icon"
                    disabled={isTyping}
                    className="shrink-0 shadow-lg bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70"
                    style={{
                      boxShadow: "0 0 20px rgba(59, 130, 246, 0.4)",
                    }}
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </motion.div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
