"use client";

import { useState, useRef, useEffect, useCallback, FormEvent } from "react";
import ReactMarkdown from "react-markdown";


interface Message {
  role: "user" | "assistant";
  content: string;
}

const EXAMPLE_QUERIES = [
  "What's the weather in Tokyo?",
  "Is it going to rain in London today?",
  "Give me a 5-day forecast for New York",
  "What's the temperature in Paris right now?",
  "How's the weather in Sydney?",
];

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
      setIsStreaming(true);

      // Add empty assistant message that we'll stream into
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      try {
        const url = `/api/chat/stream?message=${encodeURIComponent(trimmed)}`;
        const eventSource = new EventSource(url);

        eventSource.addEventListener("message", (e) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === "assistant") {
              updated[updated.length - 1] = {
                ...last,
                content: last.content + e.data,
              };
            }
            return updated;
          });
        });

        eventSource.addEventListener("done", () => {
          eventSource.close();
          setIsStreaming(false);
        });

        eventSource.addEventListener("error", () => {
          eventSource.close();
          setIsStreaming(false);
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last.role === "assistant") {
              updated[updated.length - 1] = {
                ...last,
                content: last.content
                  ? last.content +
                    "\n\n[Connection lost. Response may be incomplete.]"
                  : "Sorry, something went wrong. Please try again.",
              };
            }
            return updated;
          });
        });
      } catch {
        setIsStreaming(false);
      }
    },
    [isStreaming]
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-900">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-gray-700 bg-gray-850 px-3 py-3 sm:px-6 sm:py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
              W
            </div>
            <h1 className="text-lg font-semibold text-gray-100">WeatherWise</h1>
          </div>
          <span className="text-xs text-gray-500">
            Developed by{" "}
            <span className="text-blue-400 font-medium">Gaurav Singh</span>
          </span>
        </div>
      </header>

      {/* Messages area */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-3 py-4 sm:px-4 sm:py-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[60vh] gap-4 sm:gap-6">
              <div className="w-16 h-16 rounded-2xl bg-blue-600/20 flex items-center justify-center">
                <svg
                  className="w-8 h-8 text-blue-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z"
                  />
                </svg>
              </div>
              <div className="text-center">
                <h2 className="text-xl font-semibold text-gray-100 mb-2">
                  What&apos;s the weather like?
                </h2>
                <p className="text-gray-500 text-sm">
                  Ask me about weather conditions, forecasts, and more.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row sm:flex-wrap justify-center gap-2 w-full sm:max-w-lg">
                {EXAMPLE_QUERIES.map((query) => (
                  <button
                    key={query}
                    onClick={() => sendMessage(query)}
                    aria-label={`Ask: ${query}`}
                    className="px-3 py-2 text-sm rounded-xl bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-gray-100 border border-gray-700 transition-colors cursor-pointer text-left sm:text-center"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4" role="log" aria-live="polite">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[90%] sm:max-w-[80%] rounded-2xl px-3 py-2.5 sm:px-4 sm:py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white rounded-br-md whitespace-pre-wrap"
                        : "bg-gray-800 text-gray-200 rounded-bl-md"
                    }`}
                  >
                    {msg.role === "assistant" && msg.content ? (
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => (
                            <p className="mb-2 last:mb-0">{children}</p>
                          ),
                          strong: ({ children }) => (
                            <strong className="font-semibold text-gray-100">
                              {children}
                            </strong>
                          ),
                          ul: ({ children }) => (
                            <ul className="list-disc ml-4 mb-2 space-y-1">
                              {children}
                            </ul>
                          ),
                          ol: ({ children }) => (
                            <ol className="list-decimal ml-4 mb-2 space-y-1">
                              {children}
                            </ol>
                          ),
                          h1: ({ children }) => (
                            <h1 className="text-base font-bold text-gray-100 mb-1">
                              {children}
                            </h1>
                          ),
                          h2: ({ children }) => (
                            <h2 className="text-base font-bold text-gray-100 mb-1">
                              {children}
                            </h2>
                          ),
                          h3: ({ children }) => (
                            <h3 className="text-sm font-bold text-gray-100 mb-1">
                              {children}
                            </h3>
                          ),
                          code: ({ children }) => (
                            <code className="bg-gray-700 px-1.5 py-0.5 rounded text-xs">
                              {children}
                            </code>
                          ),
                          pre: ({ children }) => (
                            <pre className="bg-gray-700 rounded-lg p-3 overflow-x-auto mb-2 text-xs">
                              {children}
                            </pre>
                          ),
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    ) : (
                      msg.content
                    )}
                    {msg.role === "assistant" &&
                      !msg.content &&
                      isStreaming && (
                        <span className="inline-flex gap-1">
                          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" />
                        </span>
                      )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </main>

      {/* Input area */}
      <footer className="flex-shrink-0 border-t border-gray-700 bg-gray-850 px-3 py-3 sm:px-4 sm:py-4">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto flex gap-2 sm:gap-3 items-end"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the weather..."
            aria-label="Message input"
            rows={1}
            className="flex-1 resize-none rounded-xl bg-gray-800 border border-gray-600 px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            aria-label="Send message"
            className="flex-shrink-0 w-11 h-11 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white flex items-center justify-center transition-colors cursor-pointer"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18"
              />
            </svg>
          </button>
        </form>
      </footer>
    </div>
  );
}
