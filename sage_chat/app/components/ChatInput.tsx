'use client';

import { useRef, useEffect, useState, KeyboardEvent } from 'react';
import { getChannels, ChannelItem } from '../../lib/api';

interface ChatInputProps {
  onSubmit: (text: string) => void;
  onStop?: () => void;
  disabled: boolean;
  placeholder?: string;
  mode?: 'ephemeral' | 'conversation';
  onModeChange?: (mode: 'ephemeral' | 'conversation') => void;
  floating?: boolean;
}

/**
 * Builds an HTML string from raw text, wrapping valid @mentions in a blurple highlight span.
 * Text is HTML-escaped before processing so injected HTML is safe.
 */
function buildHighlightHTML(text: string, validNames: Set<string>): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped.replace(/@(\w+)/g, (match, name) => {
    if (validNames.has(name.toLowerCase())) {
      return `<span style="color:#818cf8;background:rgba(99,102,241,0.15);border-radius:3px">${match}</span>`;
    }
    return match;
  });
}

export default function ChatInput({
  onSubmit, onStop, disabled, placeholder,
  mode = 'ephemeral', onModeChange, floating = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef   = useRef<HTMLDivElement>(null);

  // Mirror state — tracks textarea value so the highlight layer re-renders
  const [inputValue, setInputValue] = useState('');
  // Set of lowercase channel names (without @) used to validate highlights
  const [validChannelNames, setValidChannelNames] = useState<Set<string>>(new Set());

  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionResults, setMentionResults] = useState<ChannelItem[]>([]);
  const [mentionVisible, setMentionVisible] = useState(6);
  const [mentionIndex, setMentionIndex] = useState(0);
  const channelCacheRef = useRef<ChannelItem[] | null>(null);
  const mentionStartRef = useRef<number>(-1);
  const [mentionScrolled, setMentionScrolled] = useState(false);

  // Focus textarea on any printable keypress
  useEffect(() => {
    const handleGlobalKey = (e: globalThis.KeyboardEvent) => {
      const el = textareaRef.current;
      if (!el) return;
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (document.activeElement as HTMLElement)?.isContentEditable) return;
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) el.focus();
    };
    window.addEventListener('keydown', handleGlobalKey);
    return () => window.removeEventListener('keydown', handleGlobalKey);
  }, []);

  const detectMention = (value: string, cursorPos: number) => {
    const textBefore = value.slice(0, cursorPos);
    const atMatch = textBefore.match(/@(\w*)$/);
    if (!atMatch) {
      setMentionQuery(null);
      return;
    }
    const query = atMatch[1].toLowerCase();
    mentionStartRef.current = cursorPos - atMatch[0].length;
    setMentionQuery(query);
    setMentionIndex(0);
    setMentionVisible(6);
    setMentionScrolled(false);

    const applyChannels = (channels: ChannelItem[]) => {
      // Build valid name set for highlight layer
      setValidChannelNames(new Set(channels.map((ch) => ch.name.replace(/^@/, '').toLowerCase())));
      // Filter for dropdown
      const filtered = query
        ? channels.filter((ch) => ch.name.toLowerCase().includes(query))
        : channels;
      setMentionResults(filtered);
    };

    if (channelCacheRef.current) {
      applyChannels(channelCacheRef.current);
    } else {
      getChannels().then((r) => {
        channelCacheRef.current = r.channels;
        applyChannels(r.channels);
      }).catch(() => {});
    }
  };

  const insertMention = (channelName: string) => {
    const el = textareaRef.current;
    if (!el) return;
    const before = el.value.slice(0, mentionStartRef.current);
    const after = el.value.slice(el.selectionStart ?? el.value.length);
    const insert = `@${channelName.replace(/^@/, '')} `;
    el.value = before + insert + after;
    setInputValue(el.value);
    const newCursor = before.length + insert.length;
    el.setSelectionRange(newCursor, newCursor);
    setMentionQuery(null);
    setMentionResults([]);
    el.focus();
  };

  const handleSubmit = () => {
    const el = textareaRef.current;
    if (!el) return;
    const text = el.value.trim();
    if (!text || disabled) return;
    el.value = '';
    setInputValue('');
    setMentionQuery(null);
    setMentionResults([]);
    onSubmit(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionQuery !== null && mentionResults.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionIndex((i) => (i + 1) % mentionResults.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionIndex((i) => (i - 1 + mentionResults.length) % mentionResults.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        insertMention(mentionResults[mentionIndex].name);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionQuery(null);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className={floating
      ? 'absolute bottom-6 left-0 right-0 px-4'
      : 'relative border-t border-[var(--border-primary)] bg-[var(--bg-base)] px-4 pb-3 pt-2.5'
    }>
      <div className="relative max-w-3xl mx-auto">
        {/* @-mention dropdown */}
        {mentionQuery !== null && mentionResults.length > 0 && (
          <div className="absolute bottom-full left-0 right-0 mb-1 z-50">
            <div
              className={`${mentionScrolled ? '' : 'mention-scroll'} rounded-xl border border-[var(--border-primary)] shadow-xl overflow-y-auto`}
              style={{
                background: 'var(--bg-elevated)',
                backdropFilter: 'blur(12px)',
                maxHeight: '13.5rem',
              }}
              onScroll={(e) => {
                const el = e.currentTarget;
                setMentionScrolled(true);
                if (el.scrollHeight - el.scrollTop - el.clientHeight < 40) {
                  setMentionVisible((v) => Math.min(v + 6, mentionResults.length));
                }
              }}
            >
              {mentionResults.slice(0, mentionVisible).map((ch, i) => (
                <button
                  key={ch.name}
                  onMouseDown={(e) => { e.preventDefault(); insertMention(ch.name); }}
                  className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors ${
                    i === mentionIndex
                      ? 'bg-indigo-600/20 text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                  }`}
                >
                  <span className="text-xs font-medium">@{ch.name.replace(/^@/, '')}</span>
                  <span className="text-[10px] text-[var(--text-dim)]">{ch.video_count} videos</span>
                </button>
              ))}
              {mentionVisible < mentionResults.length && (
                <p className="text-center text-[10px] text-[var(--text-faint)] py-1.5">scroll for more</p>
              )}
            </div>
          </div>
        )}

        <div
          className="flex items-center gap-2 rounded-2xl px-3 py-2.5 transition-colors focus-within:ring-1 focus-within:ring-[#6570fc]/40"
          style={{
            background: 'var(--input-bg)',
            backdropFilter: 'blur(12px)',
            border: '1px solid var(--input-border)',
            ...(floating ? { boxShadow: '0 8px 40px rgba(0,0,0,0.45), 0 2px 12px rgba(0,0,0,0.3)' } : {}),
          }}
        >
          {/* Q / D switch pill */}
          <div className="flex-shrink-0 border-r border-[var(--border-primary)] pr-2">
            <div
              className="flex items-center rounded-full p-0.5 gap-0.5 w-[4.5rem]"
              style={{ background: 'rgba(101,112,252,0.08)', border: '1px solid rgba(101,112,252,0.18)' }}
              title={mode === 'ephemeral' ? 'Quick Query mode' : 'Deep Dive mode'}
            >
              <button
                onClick={() => onModeChange?.('ephemeral')}
                className={`flex-1 rounded-full text-[9px] font-bold flex items-center justify-center h-5 transition-all ${
                  mode === 'ephemeral'
                    ? 'text-[var(--pill-active-text)]'
                    : 'text-[var(--text-dim)] hover:text-[var(--text-muted)]'
                }`}
                style={mode === 'ephemeral' ? {
                  background: 'rgba(101,112,252,0.3)',
                  textShadow: '0 0 8px rgba(101,112,252,0.8)',
                } : {}}
              >Quick</button>
              <button
                onClick={() => onModeChange?.('conversation')}
                className={`flex-1 rounded-full text-[9px] font-bold flex items-center justify-center h-5 transition-all ${
                  mode === 'conversation'
                    ? 'text-[var(--pill-active-text)]'
                    : 'text-[var(--text-dim)] hover:text-[var(--text-muted)]'
                }`}
                style={mode === 'conversation' ? {
                  background: 'rgba(101,112,252,0.3)',
                  textShadow: '0 0 8px rgba(101,112,252,0.8)',
                } : {}}
              >Deep</button>
            </div>
          </div>

          {/* Textarea + highlight mirror wrapper — CSS Grid so both occupy same cell */}
          <div
            className="flex-1 min-w-0"
            style={{ display: 'grid' }}
          >
            {/* Highlight mirror — in normal flow, determines grid row height */}
            <div
              ref={mirrorRef}
              aria-hidden
              className="text-sm leading-relaxed pointer-events-none select-none overflow-hidden"
              style={{
                gridArea: '1/1',
                fontFamily: 'inherit',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                color: 'var(--text-body)',
                padding: 0,
                maxHeight: '15vh',
              }}
              dangerouslySetInnerHTML={{
                __html: buildHighlightHTML(inputValue, validChannelNames) + '\u200b',
              }}
            />

            {/* Actual textarea — overlays mirror, text transparent so mirror shows */}
            <textarea
              ref={textareaRef}
              rows={1}
              disabled={disabled}
              placeholder={placeholder || 'Ask Meridian anything...'}
              onKeyDown={handleKeyDown}
              onInput={(e) => {
                const el = e.currentTarget;
                setInputValue(el.value);
                detectMention(el.value, el.selectionStart ?? el.value.length);
              }}
              onScroll={(e) => {
                if (mirrorRef.current) {
                  mirrorRef.current.scrollTop = e.currentTarget.scrollTop;
                }
              }}
              className="bg-transparent border-0 resize-none focus:outline-none disabled:opacity-50 leading-relaxed text-sm placeholder-[var(--text-faintest)]"
              style={{
                gridArea: '1/1',
                maxHeight: '15vh',
                overflowY: 'auto',
                color: 'transparent',
                caretColor: 'var(--text-body)',
                padding: 0,
              }}
            />
          </div>

          {/* Send / Stop */}
          <button
            onClick={disabled ? onStop : handleSubmit}
            className="flex-shrink-0 flex items-center justify-center w-8 h-8 transition-all"
            title={disabled ? 'Stop generation' : 'Send message (Enter)'}
          >
            {disabled ? (
              <div className="w-6 h-6 rounded-full bg-red-600/80 hover:bg-red-500 flex items-center justify-center transition-colors">
                <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="4" y="4" width="16" height="16" rx="2" />
                </svg>
              </div>
            ) : (
              <svg
                className="w-5 h-5"
                style={{ color: '#6570fc', filter: 'drop-shadow(0 0 6px rgba(101,112,252,0.65))' }}
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            )}
          </button>
        </div>

        {/* Footer hints */}
        <p className="text-[10px] text-[var(--text-faint)] mt-1.5 text-center">
          Enter to send &middot; Shift+Enter for new line
        </p>
        <p className="text-[10px] text-[var(--text-faintest)] mt-0.5 text-center flex items-center justify-center gap-1">
          {mode === 'ephemeral' ? (
            <>
              <svg className="w-2.5 h-2.5 inline-block flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                <path d="M13 2L4.09 13H11L10 22L20.91 11H14L13 2Z" />
              </svg>
              Quick Query — no memory between queries
            </>
          ) : (
            <>
              <svg className="w-2.5 h-2.5 inline-block flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.14Z" />
                <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.14Z" />
              </svg>
              Deep Dive — full conversation history
            </>
          )}
        </p>
      </div>
    </div>
  );
}
