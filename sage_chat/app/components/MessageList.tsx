'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Source } from '../../lib/api';
import MessageBubble from './MessageBubble';
import TypingIndicator from './TypingIndicator';
import UnicornBackground from './UnicornBackground';

const WELCOME_PHRASES = [
  "Let's find some answers.",
  "I've got the sources. You ask the questions.",
  'Ask me anything.',
  'Ready to investigate.',
  'What are we exploring today?',
  'Ready when you are.',
  "What's on your mind?",
  'Welcome back.',
  "What do you want to know?",
  "Thousands of hours of wisdom, distilled for you.",
  "The knowledge graph is warm. Fire away.",
  "Vectors loaded. Embeddings ready. Let's go.",
  "Think of me as a consultant who never sleeps.",
  "I watched every video so you don't have to.",
  "Less scrolling, more building. Ask away.",
  "I cross-referenced 500+ talks for this. Use me.",
  "Your unfair advantage is one query away.",
  "The answer is probably in here somewhere. Let's find it.",
  "No ego, no fluff — just signal. Ask something.",
  "Great questions get great answers. What's yours?",
  "The library is open. What do you need?",
  "I remember everything. You just have to ask.",
  "Search the signal, skip the noise.",
  "Every answer has a timestamp. Let's find yours.",
];

const SUGGESTION_POOL = [
  'How do early-stage startups get their first customers?',
  'What does Paul Graham say about product-market fit?',
  'How should founders think about hiring their first 10 employees?',
  'What are the most common reasons startups fail?',
  'How do you know when to pivot your startup?',
  'What makes a great founder pitch to investors?',
  'How do you build a culture that attracts top talent?',
  'What is the best way to price a B2B SaaS product?',
  'How should founders handle co-founder conflicts?',
  'What are the signs you have found product-market fit?',
  'How do YC companies approach distribution?',
  'What are the biggest mistakes founders make in fundraising?',
  'How do you get your first 100 users?',
  'When should a startup raise a Series A?',
  'What makes a great investor update email?',
  'How do top founders manage their time and focus?',
  'What do investors look for in a seed-stage startup?',
  'How do you do effective customer discovery?',
  'What is the difference between growth and traction?',
  'How should a founder think about their personal runway?',
];

function pickRandom<T>(arr: T[], n: number): T[] {
  return [...arr].sort(() => Math.random() - 0.5).slice(0, n);
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  usage?: { prompt_tokens: number; completion_tokens: number; cost_usd: number };
  stopped?: boolean;
}

interface MessageListProps {
  messages: ChatMessage[];
  loading: boolean;
  onSuggestionClick?: (text: string) => void;
}

/**
 * MessageList — scrollable message container.
 * Auto-scrolls on new messages / loading changes.
 * During word-by-word reveal, instant-scrolls only if user is already near the bottom.
 */
const MessageList = React.memo(function MessageList({ messages, loading, onSuggestionClick }: MessageListProps) {
  const containerRef  = useRef<HTMLDivElement>(null);
  const bottomRef     = useRef<HTMLDivElement>(null);
  const leaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollRafRef  = useRef<number | null>(null);

  const [phrase, setPhrase] = useState<string | null>(null);
  useEffect(() => {
    setPhrase(WELCOME_PHRASES[Math.floor(Math.random() * WELCOME_PHRASES.length)]);
  }, []);
  const [suggestions, setSuggestions] = useState<string[]>(() => pickRandom(SUGGESTION_POOL, 3));
  const [isShuffling, setIsShuffling] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);

  const shuffleSuggestions = useCallback(() => {
    if (isShuffling) return;
    setIsShuffling(true);
    setTimeout(() => {
      setSuggestions(pickRandom(SUGGESTION_POOL, 3));
      setIsShuffling(false);
    }, 160);
  }, [isShuffling]);


  // Smooth scroll on loading state change (marks start/end of a turn)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [loading]);

  // Smooth scroll when a new message is added
  const prevCountRef = useRef(0);
  useEffect(() => {
    if (messages.length !== prevCountRef.current) {
      prevCountRef.current = messages.length;
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length]);

  // Instant scroll during word-reveal only when already near the bottom.
  // Uses rAF so consecutive word-appends (33/sec) coalesce into at most one
  // layout read+write per visual frame instead of forcing a reflow every 30ms.
  useEffect(() => {
    if (scrollRafRef.current) cancelAnimationFrame(scrollRafRef.current);
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null;
      const el = containerRef.current;
      if (!el) return;
      if (el.scrollHeight - el.scrollTop - el.clientHeight < 180) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }, [messages]);

  const handleSuggestionsEnter = () => {
    if (leaveTimerRef.current) clearTimeout(leaveTimerRef.current);
    setSuggestionsOpen(true);
  };

  const handleSuggestionsLeave = () => {
    leaveTimerRef.current = setTimeout(() => setSuggestionsOpen(false), 200);
  };

  return (
    <div className="flex-1 relative bg-[var(--bg-base)]">
      {/* UnicornBackground — always mounted, never unmounts.
          Hiding with CSS preserves the WebGL context and prevents
          accumulating render loops on each home↔chat navigation. */}
      <div className={`absolute inset-0 pointer-events-none transition-opacity duration-500${messages.length === 0 && !loading ? ' opacity-100' : ' opacity-0'}`}>
        <UnicornBackground />
      </div>

      {messages.length === 0 && !loading ? (
        /* Home view */
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-8 py-10">
          {/* Content */}
          <div className="relative z-10 flex flex-col items-center w-full">
            {/* Dark radial vignette behind text */}
            <div
              className="absolute pointer-events-none"
              style={{
                width: '520px',
                height: '360px',
                background: 'radial-gradient(ellipse at center, rgba(10,10,15,0.88) 0%, rgba(10,10,15,0.65) 45%, transparent 75%)',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
              }}
            />

            {/* Actual content — above vignette */}
            <div className="relative flex flex-col items-center w-full">
              {/* Gradient title */}
              <h1
                className="text-5xl font-bold mb-2 leading-tight"
                style={{
                  background: 'linear-gradient(135deg, #818cf8 0%, #a5b4fc 50%, #c7d2fe 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                Meridian
              </h1>

              {/* Welcome phrase */}
              <p className="text-white/80 text-lg mb-1">{phrase ?? ''}</p>
              <p className="text-white/60 text-base max-w-xs leading-relaxed">
                Ask anything from the cornucopia of knowledge.
              </p>

              {/* Suggestions — hover to reveal */}
              <div
                className="relative"
                onMouseEnter={handleSuggestionsEnter}
                onMouseLeave={handleSuggestionsLeave}
              >
                <span className="mt-3 text-[11px] text-[var(--text-dim)] hover:text-[var(--text-muted)] cursor-pointer select-none transition-colors">
                  Suggestions
                </span>
                {suggestionsOpen && (
                  <div className="absolute top-full left-1/2 -translate-x-1/2 w-72 flex flex-col gap-1 pt-1 max-h-64 overflow-y-auto">
                    {suggestions.map((suggestion, i) => (
                      <button
                        key={suggestion}
                        onClick={() => { setSuggestionsOpen(false); onSuggestionClick?.(suggestion); }}
                        className={`suggestion-card text-left text-[11px] text-[var(--text-dim)] bg-[var(--bg-sidebar)]/90 border border-[var(--border-primary)] rounded-lg px-3 py-2 hover:border-indigo-500/50 hover:text-[var(--text-secondary)] hover:bg-indigo-600/5 leading-snug backdrop-blur-sm ${
                          isShuffling ? 'suggestion-card-exit' : 'suggestion-card-enter'
                        }`}
                        style={{ animationDelay: `${i * 40}ms` }}
                      >
                        <span className="text-indigo-500/50 mr-1.5">→</span>
                        {suggestion}
                      </button>
                    ))}
                    <button
                      onClick={shuffleSuggestions}
                      disabled={isShuffling}
                      className="mt-0.5 flex items-center justify-center gap-1.5 text-[10px] text-[var(--text-faintest)] hover:text-[var(--text-dim)] transition-colors py-0.5 disabled:opacity-50"
                    >
                      <svg
                        className={`w-3 h-3 transition-transform duration-300 ${isShuffling ? 'rotate-180' : ''}`}
                        viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      >
                        <path d="M17 2l4 4-4 4" />
                        <path d="M3 11V9a4 4 0 0 1 4-4h14" />
                        <path d="M7 22l-4-4 4-4" />
                        <path d="M21 13v2a4 4 0 0 1-4 4H3" />
                      </svg>
                      shuffle
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Chat scroll container */
        <div ref={containerRef} className="absolute inset-0 overflow-y-auto py-4">
          <div className="max-w-3xl mx-auto w-full pb-32">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
                sources={msg.sources}
                usage={msg.usage}
                stopped={msg.stopped}
              />
            ))}
            {loading && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </div>
  );
});

export default MessageList;
