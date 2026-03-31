'use client';

import React, { useMemo, useState } from 'react';
import MeridianLogo from './MeridianLogo';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Source } from '../../lib/api';
import SourceCards from './SourceCards';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  usage?: { prompt_tokens: number; completion_tokens: number; cost_usd: number };
  stopped?: boolean;
}

const MessageBubble = React.memo(function MessageBubble({ role, content, sources = [], usage, stopped }: MessageBubbleProps) {
  const isUser = role === 'user';
  const [copied, setCopied] = useState(false);

  // Build URL map from sources
  const sourceUrlMap = useMemo(() => {
    const map: Record<string, string> = {};
    sources.forEach((s) => { map[s.src_id] = s.url; });
    return map;
  }, [sources]);

  // Preprocess content: replace [SRC_N] and [SRC_N, SRC_M, ...] with inline HTML <cite> tags.
  // This avoids splitting on citations and having separate ReactMarkdown blocks (which creates <p> per segment).
  const processedContent = useMemo(() => {
    if (isUser) return content;

    // Step 1: Deduplicate citations — keep only the LAST occurrence of each unique citation token.
    // If [SRC_3] appears three times, only the final one is kept.
    const CITATION_RE = /\[SRC_\d+(?:,\s*SRC_\d+)*\]/g;
    const lastIndexMap = new Map<string, number>();
    let sm: RegExpExecArray | null;
    const scanRe = new RegExp(CITATION_RE.source, 'g');
    while ((sm = scanRe.exec(content)) !== null) {
      lastIndexMap.set(sm[0], sm.index);
    }
    let deduped = '';
    let pos = 0;
    const dedupRe = new RegExp(CITATION_RE.source, 'g');
    let dm: RegExpExecArray | null;
    while ((dm = dedupRe.exec(content)) !== null) {
      deduped += content.slice(pos, dm.index);
      if (lastIndexMap.get(dm[0]) === dm.index) deduped += dm[0];
      pos = dm.index + dm[0].length;
    }
    deduped += content.slice(pos);

    // Cleanup: dedup can leave orphaned spaces before punctuation (e.g. "Boris . Mike" when
    // a repeated [SRC_N] between "Boris" and "." gets removed). Step 2 can't catch this
    // because the citation token is already gone. Space before .!? is never valid in prose.
    deduped = deduped.replace(/ +([.!?])/g, '$1');

    // Step 2: If a citation sits before punctuation (e.g. "word [SRC_1]."), move the punctuation
    // in front and preserve the space: "word. [SRC_1]". Captures optional leading space so it
    // doesn't get stranded before the period ("word .[SRC_1]" was the old bug).
    let processed = deduped.replace(
      /( ?)(\[SRC_\d+(?:,\s*SRC_\d+)*\])([\.\!\?])/g,
      '$3$1$2'
    );

    // Step 2b: Remove space between punctuation and a following citation ("word. [SRC_1]" → "word.[SRC_1]")
    processed = processed.replace(/([\.\!\?]) (\[SRC_\d+(?:,\s*SRC_\d+)*\])/g, '$1$2');

    // Step 3: Replace [SRC_N] and [SRC_N, SRC_M, ...] with <cite> tags
    processed = processed.replace(/\[SRC_(\d+(?:,\s*SRC_\d+)*)\]/g, (_, ids) => {
      const nums = ids.match(/\d+/g)?.join(',') ?? '';
      return `<cite data-ids="${nums}"></cite>`;
    });

    return processed;
  }, [content, isUser]);

  const handleCopy = () => {
    const clean = content.replace(/\[SRC_\d+(?:,\s*SRC_\d+)*\]/g, '').replace(/\s{2,}/g, ' ').trim();
    navigator.clipboard.writeText(clean).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-2 animate-slide-in">
        <div className="max-w-[75%] bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 px-4 py-2 animate-slide-in">
      {/* Meridian avatar */}
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[var(--bg-avatar)] border border-[var(--border-avatar)] flex items-center justify-center mt-0.5">
        <MeridianLogo size={18} gradientId="mlg-bubble" />
      </div>

      <div className="flex-1 min-w-0 relative group/bubble">
        {/* Message bubble — full width */}
        <div className="markdown-content bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-[var(--text-body)]">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={{
              // Render <cite data-ids="3,4"> as inline superscript buttons
              cite: ({ node, ...props }: any) => {
                const ids: string[] = ((props as any)['data-ids'] ?? '').split(',').filter(Boolean);
                return (
                  <>
                    {ids.map((id: string) => {
                      const srcId = `SRC_${id.trim()}`;
                      const url = sourceUrlMap[srcId];
                      return url ? (
                        <sup key={id} style={{ display: 'inline', lineHeight: 0 }}>
                          <button
                            className="text-[9px] font-bold text-indigo-400 bg-indigo-500/15 border border-indigo-500/30 rounded px-[3px] mx-[1px] hover:bg-indigo-500/30 hover:text-indigo-300 transition-colors"
                            style={{ verticalAlign: 'super', fontSize: '9px', lineHeight: '1', padding: '0 2px' }}
                            onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}
                            title={`Source ${id.trim()} — open on YouTube`}
                          >
                            {id.trim()}
                          </button>
                        </sup>
                      ) : (
                        <sup key={id} style={{ display: 'inline', lineHeight: 0 }}>
                          <span
                            className="text-[9px] font-bold text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 rounded mx-[1px]"
                            style={{ verticalAlign: 'super', fontSize: '9px', lineHeight: '1', padding: '0 2px' }}
                          >
                            {id.trim()}
                          </span>
                        </sup>
                      );
                    })}
                  </>
                );
              },
            }}
          >
            {processedContent}
          </ReactMarkdown>
        </div>

        {/* Copy icon — absolutely positioned outside the right edge, no layout impact */}
        <button
          onClick={handleCopy}
          className="absolute top-1 -right-7 pb-4 pt-2 px-1 opacity-0 group-hover/bubble:opacity-100 transition-opacity text-[var(--text-dim)] hover:text-[var(--text-secondary)]"
          title={copied ? 'Copied!' : 'Copy response'}
        >
          {copied ? (
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
          )}
        </button>

        {/* Stopped indicator */}
        {stopped && (
          <p className="mt-1.5 px-1 text-[11px] text-[var(--text-muted)] italic">— response stopped</p>
        )}

        {/* Combined meta row: sources toggle + usage */}
        {(sources.length > 0 || usage) && (
          <SourceCards sources={sources} usage={usage} />
        )}
      </div>
    </div>
  );
});

export default MessageBubble;
