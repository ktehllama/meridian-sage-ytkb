'use client';

interface ModeToggleProps {
  mode: 'ephemeral' | 'conversation';
  onModeChange: (mode: 'ephemeral' | 'conversation') => void;
}

/**
 * ModeToggle — pill toggle between Quick Query (ephemeral) and Deep Dive (conversation).
 * Switching mode clears chat history (handled by parent via onModeChange).
 */
export default function ModeToggle({ mode, onModeChange }: ModeToggleProps) {
  return (
    <div
      className="flex items-center gap-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-full p-0.5"
      title="Toggle between Quick Query (stateless) and Deep Dive (full conversation history)"
    >
      <button
        onClick={() => onModeChange('ephemeral')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ${
          mode === 'ephemeral'
            ? 'bg-indigo-600 text-white shadow-sm'
            : 'text-[#a0a0a0] hover:text-[#f0f0f0]'
        }`}
      >
        {/* Lightning bolt */}
        <svg
          className="w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path d="M13 2L4.09 13H11L10 22L20.91 11H14L13 2Z" />
        </svg>
        Quick Query
      </button>

      <button
        onClick={() => onModeChange('conversation')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ${
          mode === 'conversation'
            ? 'bg-indigo-600 text-white shadow-sm'
            : 'text-[#a0a0a0] hover:text-[#f0f0f0]'
        }`}
      >
        {/* Brain icon */}
        <svg
          className="w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.14Z" />
          <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.14Z" />
        </svg>
        Deep Dive
      </button>
    </div>
  );
}
