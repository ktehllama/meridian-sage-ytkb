'use client';

import { useState } from 'react';
import { Source } from '../../lib/api';

interface SourceCardsProps {
  sources: Source[];
  usage?: { prompt_tokens: number; completion_tokens: number; cost_usd: number };
}

/**
 * SourceCards — collapsible dropdown list of source cards shown below assistant messages.
 * Default: collapsed. Click to expand and show individual source links.
 * Also renders token usage inline with the sources toggle.
 */
export default function SourceCards({ sources, usage }: SourceCardsProps) {
  const [open, setOpen] = useState(false);

  if (!sources || (sources.length === 0 && !usage)) return null;

  return (
    <div className="mt-1.5">
      {/* Toggle row: sources toggle on left, usage on right */}
      <div className="flex items-center justify-between">
        {sources.length > 0 ? (
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1.5 text-[10px] text-[var(--text-dim)] hover:text-[var(--text-muted)] transition-colors"
          >
            <svg
              className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`}
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
            >
              <path d="M9 18l6-6-6-6" />
            </svg>
            <span>{sources.length} source{sources.length !== 1 ? 's' : ''}</span>
          </button>
        ) : <span />}

        {usage && (
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-dim)] font-mono">
            <svg className="w-3 h-3 text-[var(--text-faint)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/>
            </svg>
            <span>{usage.prompt_tokens.toLocaleString()}</span>
            <span className="text-[var(--text-faintest)]">/</span>
            <span>{usage.completion_tokens.toLocaleString()}</span>
            <span className="text-[var(--text-faintest)]">·</span>
            <span className="text-[var(--text-dim)]">${usage.cost_usd.toFixed(5)}</span>
          </div>
        )}
      </div>

      {/* Expanded list */}
      {open && (
        <div className="mt-1.5 space-y-1">
          {sources.map((source) => (
            <a
              key={source.src_id}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--bg-hover)] transition-colors group"
            >
              {/* Source number badge */}
              <span className="flex-shrink-0 text-[9px] font-bold text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 rounded px-1.5 py-0.5 mt-0.5">
                {source.src_id.replace('SRC_', '')}
              </span>

              <div className="flex-1 min-w-0">
                {/* Title + timestamp */}
                <div className="flex items-baseline gap-1.5">
                  <span className="text-[11px] font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] truncate leading-snug">
                    {source.title}
                  </span>
                  <span className="flex-shrink-0 text-[9px] text-[var(--text-dim)] font-mono">{source.timestamp_str}</span>
                </div>
                {/* Quote */}
                <p className="text-[10px] text-[var(--text-muted)] italic line-clamp-2 mt-0.5">
                  &ldquo;{source.quote}&rdquo;
                </p>
              </div>

              {/* YouTube icon */}
              <svg className="flex-shrink-0 w-3 h-3 text-[var(--text-faintest)] group-hover:text-red-500 transition-colors mt-0.5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
              </svg>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
