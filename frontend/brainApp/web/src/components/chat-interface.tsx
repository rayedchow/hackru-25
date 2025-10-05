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
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface Message {
  id: number;
  text: string;
  sender: "user" | "bot";
  timestamp?: string;
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

  const handleSend = () => {
    if (input.trim()) {
      const newMessage = {
        id: messages.length + 1,
        text: input,
        sender: "user" as const,
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };
      setMessages([...messages, newMessage]);
      setInput("");

      setIsTyping(true);
      setTimeout(() => {
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          {
            id: prev.length + 1,
            text: "I'm processing your request...",
            sender: "bot",
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);
      }, 1500);
    }
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
      <div className="flex items-center justify-between border-b border-border/50 bg-gradient-to-r from-background/40 to-background/20 px-6 py-4 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <div className="h-3 w-3 rounded-full bg-red-500/60" />
            <div className="h-3 w-3 rounded-full bg-yellow-500/60" />
            <div className="h-3 w-3 rounded-full bg-green-500/60" />
          </div>
          <motion.h1
            className="font-mono text-sm text-foreground/70 flex items-center gap-2"
            animate={{ opacity: isTyping ? [1, 0.5, 1] : 1 }}
            transition={{
              duration: 1.5,
              repeat: isTyping ? Number.POSITIVE_INFINITY : 0,
            }}
          >
            {isTyping ? "Listening..." : "Touch Desk"}
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
        <div className="text-xs text-muted-foreground font-mono">
          Ready for Screenshots
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        <AnimatePresence>
          {messages.map((message, index) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.05 }}
              className={`flex ${
                message.sender === "user" ? "justify-end" : "justify-start"
              }`}
              onMouseEnter={() => setHoveredMessage(message.id)}
              onMouseLeave={() => setHoveredMessage(null)}
            >
              <div className="flex flex-col gap-1 max-w-[80%]">
                <div
                  className={`flex items-center gap-1.5 px-2 ${
                    message.sender === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {message.sender === "bot" && (
                    <Sparkles className="h-3 w-3 text-primary" />
                  )}
                  <span className="text-xs text-muted-foreground font-mono">
                    {message.sender === "bot" ? "AI Assistant" : "You"}
                  </span>
                  <span className="text-xs text-muted-foreground/50">
                    {message.timestamp}
                  </span>
                </div>

                <motion.div
                  whileHover={{ scale: 1.02 }}
                  className={`relative rounded-2xl px-5 py-3 backdrop-blur-sm ${
                    message.sender === "user"
                      ? "bg-primary/90 text-primary-foreground border border-primary/30 shadow-lg shadow-primary/20"
                      : "bg-gradient-to-br from-card/90 to-card/70 text-card-foreground border border-border/40 shadow-xl"
                  }`}
                  style={
                    message.sender === "user"
                      ? {
                          boxShadow:
                            "0 0 20px rgba(59, 130, 246, 0.3), 0 4px 12px rgba(0, 0, 0, 0.2)",
                        }
                      : {}
                  }
                >
                  <p className="text-sm leading-relaxed">{message.text}</p>

                  <AnimatePresence>
                    {hoveredMessage === message.id && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        className="absolute -top-8 right-0 flex gap-1 bg-background/95 backdrop-blur-md border border-border/50 rounded-lg p-1 shadow-lg"
                      >
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-6 w-6"
                          onClick={() =>
                            navigator.clipboard.writeText(message.text)
                          }
                        >
                          <Copy className="h-3 w-3" />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-6 w-6">
                          <Bookmark className="h-3 w-3" />
                        </Button>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

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

      <div className="border-t border-border/50 bg-gradient-to-r from-background/40 to-background/20 p-4 backdrop-blur-sm">
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask about your screenshots or type a message..."
            className="flex-1 bg-background/60 backdrop-blur-sm border-border/50 font-mono text-sm focus:ring-2 focus:ring-primary/50"
          />
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Button
              onClick={handleSend}
              size="icon"
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
    </div>
  );
}
