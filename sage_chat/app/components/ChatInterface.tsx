'use client';

import { useReducer, useCallback, useEffect, useRef, useState } from 'react';
import { chat, getHealth, Message, Source, ApiError, calcCost, getBudgetSpent, addBudgetSpent, getBudgetCap, setBudgetCap, loadChats, saveChat, deleteChat, renameChat, newChatId, StoredChat, formatModelName } from '../../lib/api';
import MessageList, { ChatMessage } from './MessageList';
import { generateChatName } from '../../lib/chatName';
import ChatInput from './ChatInput';
import Sidebar from './Sidebar';
import SettingsPanel from './SettingsPanel';
import MeridianLogo from './MeridianLogo';

// ── State ──────────────────────────────────────────────────────────────────

interface State {
  messages: ChatMessage[];
  mode: 'ephemeral' | 'conversation';
  loading: boolean;
  sidebarOpen: boolean;
  error: string | null;
  turnCount: number;
}

type Action =
  | { type: 'ADD_USER_MSG'; id: string; text: string }
  | { type: 'ADD_ASSISTANT_MSG'; id: string; usage?: { prompt_tokens: number; completion_tokens: number; cost_usd: number } }
  | { type: 'APPEND_WORD'; id: string; word: string }
  | { type: 'SET_SOURCES'; id: string; sources: Source[] }
  | { type: 'MARK_STOPPED'; id: string }
  | { type: 'SET_LOADING'; loading: boolean }
  | { type: 'SET_MODE'; mode: 'ephemeral' | 'conversation' }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'CLOSE_SIDEBAR' }
  | { type: 'SET_ERROR'; error: string | null }
  | { type: 'CLEAR_CHAT' }
  | { type: 'INCREMENT_TURNS' }
  | { type: 'RESTORE_MESSAGES'; messages: ChatMessage[] };

const initialState: State = {
  messages: [],
  mode: 'ephemeral',
  loading: false,
  sidebarOpen: false,
  error: null,
  turnCount: 0,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'ADD_USER_MSG':
      return {
        ...state,
        messages: [...state.messages, { id: action.id, role: 'user', content: action.text }],
        loading: true,
        error: null,
      };

    case 'ADD_ASSISTANT_MSG':
      return {
        ...state,
        messages: [...state.messages, { id: action.id, role: 'assistant', content: '', sources: [], usage: action.usage }],
      };

    case 'APPEND_WORD': {
      const updated = state.messages.map((m) =>
        m.id === action.id
          ? { ...m, content: m.content + (m.content ? ' ' : '') + action.word }
          : m,
      );
      return { ...state, messages: updated };
    }

    case 'SET_SOURCES': {
      const updated = state.messages.map((m) =>
        m.id === action.id ? { ...m, sources: action.sources } : m,
      );
      return { ...state, messages: updated };
    }

    case 'MARK_STOPPED': {
      const updated = state.messages.map((m) =>
        m.id === action.id ? { ...m, stopped: true } : m,
      );
      return { ...state, messages: updated };
    }

    case 'SET_LOADING':
      return { ...state, loading: action.loading };

    case 'INCREMENT_TURNS':
      return { ...state, turnCount: state.turnCount + 1 };

    case 'SET_MODE':
      return { ...initialState, mode: action.mode };

    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarOpen: !state.sidebarOpen };

    case 'CLOSE_SIDEBAR':
      return { ...state, sidebarOpen: false };

    case 'SET_ERROR':
      return { ...state, error: action.error, loading: false };

    case 'CLEAR_CHAT':
      return { ...state, messages: [], error: null, turnCount: 0, loading: false };

    case 'RESTORE_MESSAGES':
      return { ...state, messages: action.messages };

    default:
      return state;
  }
}

// ── ID generator (stable between renders, no crypto needed) ───────────────
let _counter = 0;
function uid() {
  return `msg_${Date.now()}_${++_counter}`;
}

// ── Word-reveal helper ─────────────────────────────────────────────────────
function revealWords(
  words: string[],
  dispatch: React.Dispatch<Action>,
  msgId: string,
  sources: Source[],
  intervalRef: React.MutableRefObject<ReturnType<typeof setInterval> | null>,
): void {
  let i = 0;
  const interval = setInterval(() => {
    if (i < words.length) {
      dispatch({ type: 'APPEND_WORD', id: msgId, word: words[i] });
      i++;
    } else {
      clearInterval(interval);
      intervalRef.current = null;
      dispatch({ type: 'SET_SOURCES', id: msgId, sources });
      dispatch({ type: 'INCREMENT_TURNS' });
    }
  }, 30);
  intervalRef.current = interval;
}

// ── Component ──────────────────────────────────────────────────────────────

export default function ChatInterface() {
  const [state, dispatch] = useReducer(reducer, initialState);
  // Initialize to 0 (matches server render) then read localStorage on client to avoid SSR mismatch
  const [totalSpent, setTotalSpent] = useState(0);
  const [budgetCap, setBudgetCapState] = useState(300);
  const [editingBudget, setEditingBudget] = useState(false);
  const [budgetInput, setBudgetInput] = useState('');
  const [modelName, setModelName] = useState('');
  useEffect(() => {
    setTotalSpent(getBudgetSpent());
    setBudgetCapState(getBudgetCap());
    getHealth().then(h => setModelName(formatModelName(h.model))).catch(() => {});
  }, []);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const revealIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const currentChatIdRef = useRef<string | null>(null);
  const lastAssistantMsgIdRef = useRef<string | null>(null);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chatNameRef = useRef<string | null>(null);

  const messagesRef = useRef(state.messages);
  useEffect(() => { messagesRef.current = state.messages; }, [state.messages]);

  // Save messages to localStorage — debounced 600ms to avoid thrashing during word-reveal
  useEffect(() => {
    if (state.messages.length === 0) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      const id = currentChatIdRef.current ?? newChatId();
      currentChatIdRef.current = id;
      const firstUserMsg = state.messages.find(m => m.role === 'user');
      const firstAssistantMsg = state.messages.find(m => m.role === 'assistant' && m.content.length > 0);
      if (!chatNameRef.current && firstUserMsg && firstAssistantMsg) {
        chatNameRef.current = generateChatName(firstUserMsg.content, firstAssistantMsg.content);
      }
      const name = chatNameRef.current ?? firstUserMsg?.content.slice(0, 40) ?? 'Untitled';
      saveChat({ id, name, mode: state.mode, messages: state.messages, savedAt: Date.now() });
    }, 600);
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); };
  }, [state.messages, state.mode]);

  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (revealIntervalRef.current) {
      clearInterval(revealIntervalRef.current);
      revealIntervalRef.current = null;
    }
    // Mark the in-progress assistant bubble as stopped
    if (lastAssistantMsgIdRef.current) {
      dispatch({ type: 'MARK_STOPPED', id: lastAssistantMsgIdRef.current });
      lastAssistantMsgIdRef.current = null;
    }
    dispatch({ type: 'SET_LOADING', loading: false });
  }, []);

  const handleSubmit = useCallback(
    async (text: string) => {
      if (state.loading) return;

      const controller = new AbortController();
      abortRef.current = controller;

      const userMsgId = uid();
      dispatch({ type: 'ADD_USER_MSG', id: userMsgId, text });

      // Build history from current messages (before adding user message above)
      const history: Message[] =
        state.mode === 'conversation'
          ? messagesRef.current.map((m) => ({ role: m.role, content: m.content }))
          : [];

      try {
        const response = await chat(text, state.mode, history, controller.signal);

        // Compute and track cost
        let costUsd = 0;
        if (response.usage) {
          costUsd = calcCost(response.usage);
          const newTotal = addBudgetSpent(costUsd);
          setTotalSpent(newTotal);
        }

        const assistantMsgId = uid();
        lastAssistantMsgIdRef.current = assistantMsgId;
        const usageForMsg = response.usage
          ? { ...response.usage, cost_usd: costUsd }
          : undefined;
        dispatch({ type: 'ADD_ASSISTANT_MSG', id: assistantMsgId, usage: usageForMsg });
        dispatch({ type: 'SET_LOADING', loading: false });

        // Small pause so the empty bubble appears before words start appearing
        await new Promise((r) => setTimeout(r, 80));

        const words = response.answer.split(' ');
        revealWords(words, dispatch, assistantMsgId, response.sources, revealIntervalRef);
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          dispatch({ type: 'SET_LOADING', loading: false });
          return;
        }
        let message = 'Something went wrong. Please try again.';
        if (err instanceof ApiError) {
          if (err.statusCode === 503) {
            message = 'Knowledge base unavailable. Is the backend server running?';
          } else {
            message = `Error: ${err.message}`;
          }
        }
        dispatch({ type: 'SET_ERROR', error: message });
      }
    },
    [state.loading, state.mode],
  );

  const handleModeChange = useCallback((mode: 'ephemeral' | 'conversation') => {
    if (revealIntervalRef.current) { clearInterval(revealIntervalRef.current); revealIntervalRef.current = null; }
    if (saveTimerRef.current) { clearTimeout(saveTimerRef.current); saveTimerRef.current = null; }
    dispatch({ type: 'SET_MODE', mode });
  }, []);

  const handleNewChat = useCallback(() => {
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
    if (revealIntervalRef.current) { clearInterval(revealIntervalRef.current); revealIntervalRef.current = null; }
    if (saveTimerRef.current) { clearTimeout(saveTimerRef.current); saveTimerRef.current = null; }
    currentChatIdRef.current = null;
    chatNameRef.current = null;
    dispatch({ type: 'CLEAR_CHAT' });
  }, []);

  const handleVideoSelect = useCallback(
    (text: string) => {
      dispatch({ type: 'CLOSE_SIDEBAR' });
      handleSubmit(text);
    },
    [handleSubmit],
  );

  const handleRestoreChat = useCallback((storedChat: StoredChat) => {
    if (revealIntervalRef.current) { clearInterval(revealIntervalRef.current); revealIntervalRef.current = null; }
    if (saveTimerRef.current) { clearTimeout(saveTimerRef.current); saveTimerRef.current = null; }
    currentChatIdRef.current = storedChat.id;
    dispatch({ type: 'SET_MODE', mode: storedChat.mode });
    dispatch({ type: 'RESTORE_MESSAGES', messages: storedChat.messages as ChatMessage[] });
    dispatch({ type: 'CLOSE_SIDEBAR' });
  }, []);

  const handleDeleteChat = useCallback((id: string) => {
    deleteChat(id);
    if (currentChatIdRef.current === id) {
      currentChatIdRef.current = null;
      dispatch({ type: 'CLEAR_CHAT' });
    }
  }, []);

  const handleRenameChat = useCallback((id: string, name: string) => {
    renameChat(id, name);
  }, []);

  const showTurnWarning = state.mode === 'conversation' && state.turnCount >= 18;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        isOpen={state.sidebarOpen}
        onClose={() => dispatch({ type: 'CLOSE_SIDEBAR' })}
        onVideoSelect={handleVideoSelect}
        onRestoreChat={handleRestoreChat}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onNewChat={handleNewChat}
        activeChatId={currentChatIdRef.current}
      />

      {/* Settings panel */}
      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0 h-full">
        {/* Top bar */}
        <header className="relative flex items-center justify-between px-4 py-3 border-b border-[var(--border-primary)] flex-shrink-0 bg-[var(--bg-base)]">
          {/* Center — model name */}
          {modelName && state.messages.length > 0 && (
            <div className="absolute left-1/2 -translate-x-1/2 pointer-events-none">
              <span className="text-sm font-bold bg-gradient-to-r from-violet-400 via-indigo-400 to-[#BBC7FD] bg-clip-text text-transparent tracking-tight">
                {modelName}
              </span>
            </div>
          )}
          <div className="flex items-center gap-3">
            <button
              onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
              className="text-[var(--text-dim)] hover:text-[var(--text-primary)] transition-colors"
              title="Browse knowledge base"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>

            <button
              onClick={handleNewChat}
              className="flex items-center gap-2 hover:opacity-80 transition-opacity"
              title="Go to home"
            >
              <MeridianLogo size={28} gradientId="mlg-header" />
              <span className="font-semibold text-sm text-[var(--text-primary)]">Meridian</span>
            </button>
          </div>

          <div className="flex items-center gap-3">
            {editingBudget ? (
              <input
                autoFocus
                type="number"
                min="0"
                step="0.01"
                value={budgetInput}
                onChange={(e) => setBudgetInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    const val = parseFloat(budgetInput);
                    if (!isNaN(val) && val >= 0) {
                      const newCap = val + totalSpent;
                      setBudgetCap(newCap);
                      setBudgetCapState(newCap);
                    }
                    setEditingBudget(false);
                  }
                  if (e.key === 'Escape') setEditingBudget(false);
                }}
                onBlur={() => {
                  const val = parseFloat(budgetInput);
                  if (!isNaN(val) && val >= 0) {
                    const newCap = val + totalSpent;
                    setBudgetCap(newCap);
                    setBudgetCapState(newCap);
                  }
                  setEditingBudget(false);
                }}
                className="w-20 text-xs font-mono text-emerald-500 bg-transparent border-b border-emerald-500/50 focus:outline-none text-right"
                suppressHydrationWarning
              />
            ) : (
              <button
                className="text-xs font-mono text-emerald-500 hover:text-emerald-400 transition-colors"
                title={`$${totalSpent.toFixed(5)} spent — click to edit budget`}
                onClick={() => { setBudgetInput((budgetCap - totalSpent).toFixed(5)); setEditingBudget(true); }}
                suppressHydrationWarning
              >
                ${(budgetCap - totalSpent).toFixed(5)} left
              </button>
            )}

            {state.messages.length > 0 && (
              <button
                onClick={handleNewChat}
                className="text-xs text-[var(--text-dim)] hover:text-[var(--text-primary)] transition-colors px-2 py-1 rounded border border-[var(--border-primary)] hover:border-[var(--text-faintest)]"
              >
                New Chat
              </button>
            )}

            {/* Settings */}
            <button
              onClick={() => setSettingsOpen(true)}
              className="text-[var(--text-dim)] hover:text-[var(--text-primary)] transition-colors"
              title="Settings"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
          </div>
        </header>

        {/* Warnings and errors */}
        {showTurnWarning && (
          <div className="px-4 py-2 bg-amber-900/20 border-b border-amber-700/30 text-xs text-amber-400 text-center">
            Long conversation — nearing token limit. Consider starting a New Chat.
          </div>
        )}

        {state.error && (
          <div className="mx-4 mt-3 px-4 py-3 bg-red-900/20 border border-red-700/30 rounded-lg text-xs text-red-400 flex items-start justify-between gap-3">
            <span>{state.error}</span>
            <button
              onClick={() => dispatch({ type: 'SET_ERROR', error: null })}
              className="text-red-400/60 hover:text-red-400 flex-shrink-0"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Message list + floating input */}
        <div className="relative flex flex-col flex-1 min-h-0">
          <MessageList
            messages={state.messages}
            loading={state.loading}
            onSuggestionClick={handleSubmit}
          />

          <ChatInput
            onSubmit={handleSubmit}
            onStop={handleStop}
            disabled={state.loading}
            mode={state.mode}
            onModeChange={handleModeChange}
            floating
            placeholder={
              state.mode === 'ephemeral'
                ? 'Ask anything...'
                : 'Continue the conversation...'
            }
          />
        </div>
      </div>
    </div>
  );
}
