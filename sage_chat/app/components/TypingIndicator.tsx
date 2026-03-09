'use client';

import MeridianLogo from './MeridianLogo';

/**
 * TypingIndicator — animated three-dot bounce shown while waiting for a response.
 */
export default function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      {/* Avatar */}
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[var(--bg-avatar)] border border-[var(--border-avatar)] flex items-center justify-center">
        <MeridianLogo size={18} gradientId="mlg-typing" />
      </div>
      {/* Dots */}
      <div className="flex items-center gap-1.5 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-2xl rounded-tl-sm px-4 py-3">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="block w-2 h-2 rounded-full bg-indigo-400 animate-bounce-dot"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </div>
    </div>
  );
}
