'use client';

import { useState, useEffect } from 'react';
import { getVideos, getChannels, VideoItem, ChannelItem, formatDuration, loadChats, initChatsFromServer, StoredChat } from '../../lib/api';
import { ALL_CATEGORIES, getCategoryForChannel } from '../../lib/channelCategories';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onVideoSelect: (title: string) => void;
  onRestoreChat?: (chat: StoredChat) => void;
  onDeleteChat?: (id: string) => void;
  onRenameChat?: (id: string, name: string) => void;
  onNewChat?: () => void;
  activeChatId?: string | null;
}

function relativeTime(ts: number): string {
  const now = Date.now();
  const diffMs = now - ts;
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30.44);

  if (diffMin < 60) return diffMin <= 1 ? 'just now' : `${diffMin} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffWeeks < 4) return `${diffWeeks} week${diffWeeks !== 1 ? 's' : ''} ago`;
  if (diffMonths < 6) return `${diffMonths} month${diffMonths !== 1 ? 's' : ''} ago`;
  if (diffMonths < 12) return 'half a year ago';
  // ≥ 1 year — show actual date
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Sidebar — collapsible drawer showing chats, video, and channel browser.
 * Clicking a saved chat restores it. Clicking a video title seeds a new query.
 */
export default function Sidebar({ isOpen, onClose, onVideoSelect, onRestoreChat, onDeleteChat, onRenameChat, onNewChat, activeChatId }: SidebarProps) {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [channels, setChannels] = useState<ChannelItem[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [search, setSearch] = useState('');
  const [total, setTotal] = useState(0);
  const [allTotal, setAllTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [tab, setTab] = useState<'chats' | 'channels' | 'videos'>('chats');
  const [savedChats, setSavedChats] = useState<StoredChat[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');

  // Load saved chats from server when sidebar opens
  useEffect(() => {
    if (!isOpen) return;
    initChatsFromServer()
      .then(() => setSavedChats(loadChats()))
      .catch(() => setSavedChats(loadChats()));
  }, [isOpen]);

  // Load channels and all-channels total count on open
  useEffect(() => {
    if (!isOpen) return;
    getChannels()
      .then((r) => setChannels(r.channels))
      .catch(() => {});
    // Fetch total video count across all channels (no filter)
    getVideos(undefined, 1, 0)
      .then((r) => setAllTotal(r.total))
      .catch(() => {});
  }, [isOpen]);

  // Load videos when channel filter changes (reset + initial fetch)
  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setHasMore(false);
    const limit = 200;
    getVideos(selectedChannel || undefined, limit, 0)
      .then((r) => {
        setVideos(r.videos);
        setTotal(r.total);
        setHasMore(r.videos.length === limit && r.total > limit);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [isOpen, selectedChannel]);

  const loadMoreVideos = () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    const limit = 200;
    getVideos(selectedChannel || undefined, limit, videos.length)
      .then((r) => {
        const merged = [...videos, ...r.videos];
        setVideos(merged);
        setHasMore(r.videos.length === limit && merged.length < r.total);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  };

  const filteredVideos = search
    ? videos.filter((v) => v.title.toLowerCase().includes(search.toLowerCase()))
    : videos;

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-30"
        onClick={onClose}
      />

      {/* Drawer */}
      <aside className="fixed left-0 top-0 h-full w-72 bg-[var(--bg-sidebar)] border-r border-[var(--border-primary)] z-40 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-[var(--border-primary)]">
          <span className="font-semibold text-sm text-[var(--text-primary)]">Knowledge Base</span>
          <button
            onClick={onClose}
            className="text-[var(--text-dim)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--border-primary)]">
          {(['chats', 'channels', 'videos'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-2.5 text-xs font-medium capitalize transition-colors ${
                tab === t
                  ? 'text-indigo-400 border-b-2 border-indigo-500'
                  : 'text-[var(--text-dim)] hover:text-[var(--text-muted)]'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === 'chats' && (
          <div className="flex flex-col flex-1 min-h-0">
            {/* New Chat button */}
            <div className="px-3 pt-3 pb-2 border-b border-[var(--bg-hover)]">
              <button
                onClick={(e) => { e.stopPropagation(); onNewChat?.(); onClose(); }}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-dashed border-[var(--border-primary)] text-xs text-[var(--text-dim)] hover:border-indigo-500/40 hover:text-indigo-400 transition-all"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New Chat
              </button>
            </div>

            {/* Chat list */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {savedChats.length === 0 ? (
                <p className="text-[11px] text-[var(--text-faint)] text-center mt-8">No saved chats yet.</p>
              ) : savedChats.map((sc) => {
                const isActive = sc.id === activeChatId;
                const isEditing = editingId === sc.id;
                const time = relativeTime(sc.savedAt);

                return (
                  <div
                    key={sc.id}
                    className={`group relative rounded-lg border transition-all ${
                      isActive
                        ? 'bg-indigo-600/10 border-indigo-500/30'
                        : 'bg-[var(--bg-elevated)] border-[var(--border-primary)] hover:border-[var(--border-subtle)]'
                    }`}
                  >
                    {/* Main click area */}
                    <button
                      onClick={() => !isEditing && onRestoreChat?.(sc)}
                      className="w-full text-left px-3 py-2.5 pr-16"
                    >
                      {/* Name row */}
                      {isEditing ? (
                        <input
                          autoFocus
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              onRenameChat?.(sc.id, editingName.trim() || sc.name);
                              setSavedChats(prev => prev.map(c => c.id === sc.id ? { ...c, name: editingName.trim() || c.name } : c));
                              setEditingId(null);
                            }
                            if (e.key === 'Escape') setEditingId(null);
                          }}
                          onBlur={() => {
                            onRenameChat?.(sc.id, editingName.trim() || sc.name);
                            setSavedChats(prev => prev.map(c => c.id === sc.id ? { ...c, name: editingName.trim() || c.name } : c));
                            setEditingId(null);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full bg-[var(--border-primary)] border border-indigo-500/40 rounded px-2 py-0.5 text-xs text-[var(--text-primary)] focus:outline-none"
                        />
                      ) : (
                        <p className="text-xs font-medium text-[var(--text-secondary)] line-clamp-2 leading-snug">
                          {sc.name}
                        </p>
                      )}
                      {/* Meta row */}
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className="text-[10px] font-semibold uppercase tracking-wide text-indigo-400/70">
                          {sc.mode === 'ephemeral' ? 'Quick' : 'Deep'}
                        </span>
                        <span className="text-[10px] text-[var(--text-dim)]">·</span>
                        <span className="text-[10px] text-[var(--text-muted)]">{sc.messages.length} msgs</span>
                        <span className="text-[10px] text-[var(--text-dim)]">·</span>
                        <span className="text-[10px] text-[var(--text-muted)]">{time}</span>
                      </div>
                    </button>

                    {/* Action buttons — shown on hover */}
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {/* Rename */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingId(sc.id);
                          setEditingName(sc.name);
                        }}
                        className="p-1 rounded text-[var(--text-faint)] hover:text-[var(--text-muted)] hover:bg-[var(--border-primary)] transition-colors"
                        title="Rename"
                      >
                        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
                        </svg>
                      </button>
                      {/* Delete */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteChat?.(sc.id);
                          setSavedChats(prev => prev.filter(c => c.id !== sc.id));
                        }}
                        className="p-1 rounded text-[var(--text-faint)] hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        title="Delete"
                      >
                        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="3 6 5 6 21 6"/>
                          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                          <path d="M10 11v6M14 11v6"/>
                        </svg>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {tab === 'channels' && (
          /* Channels tab */
          <div className="flex flex-col flex-1 min-h-0">
            {/* Category filter pills */}
            <div className="px-3 pt-3 pb-2 border-b border-[var(--bg-hover)]">
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => setSelectedCategory('')}
                  className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
                    !selectedCategory ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/40' : 'bg-[var(--bg-hover)] text-[var(--text-dim)] border border-[var(--border-primary)] hover:text-[var(--text-muted)]'
                  }`}
                >
                  All
                </button>
                {ALL_CATEGORIES.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat === selectedCategory ? '' : cat)}
                    className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors ${
                      selectedCategory === cat ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/40' : 'bg-[var(--bg-hover)] text-[var(--text-dim)] border border-[var(--border-primary)] hover:text-[var(--text-muted)]'
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>

            {/* Channel list filtered by category */}
            <div className="flex-1 overflow-y-auto p-3 space-y-1">
              <button
                onClick={() => setSelectedChannel('')}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-xs transition-colors ${
                  !selectedChannel ? 'bg-indigo-600/20 text-indigo-300' : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                }`}
              >
                <span className="font-medium">All channels</span>
                <span className="ml-2 text-[var(--text-dim)]">{allTotal} videos</span>
              </button>
              {channels
                .filter((ch) => !selectedCategory || getCategoryForChannel(ch.name) === selectedCategory)
                .map((ch) => (
                  <button
                    key={ch.name}
                    onClick={() => { setSelectedChannel(ch.name); setTab('videos'); }}
                    className={`w-full text-left px-3 py-2.5 rounded-lg text-xs transition-colors ${
                      selectedChannel === ch.name
                        ? 'bg-indigo-600/20 text-indigo-300'
                        : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    <span className="font-medium">{ch.name}</span>
                    <span className="ml-2 text-[var(--text-dim)]">{ch.video_count} videos</span>
                  </button>
                ))}
            </div>
          </div>
        )}

        {tab === 'videos' && (
          /* Videos tab */
          <>
            {/* Channel context header when viewing a specific channel */}
            {selectedChannel && (
              <div className="px-3 pt-3 pb-1 flex items-center gap-2">
                <button
                  onClick={() => { setSelectedChannel(''); setTab('channels'); }}
                  className="text-[#606060] hover:text-[#f0f0f0] transition-colors"
                  title="Back to all channels"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M19 12H5M12 19l-7-7 7-7"/>
                  </svg>
                </button>
                <span className="text-sm font-semibold text-indigo-300 truncate">{selectedChannel}</span>
              </div>
            )}

            {/* Search bar */}
            <div className="px-3 pt-3 pb-2">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter videos..."
                className="w-full bg-[var(--bg-elevated)] border border-[var(--border-primary)] rounded-lg px-3 py-2 text-xs text-[var(--text-primary)] placeholder-[var(--text-faint)] focus:outline-none focus:border-indigo-500/50"
              />
              <p className="text-[10px] text-[var(--text-faint)] mt-1.5">
                {loading ? 'Loading...' : `${filteredVideos.length} of ${total} videos`}
                {selectedChannel && ` in ${selectedChannel}`}
              </p>
            </div>

            {/* Video list */}
            <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-1">
              {filteredVideos.length === 0 && !loading && (
                <p className="text-[11px] text-[var(--text-faint)] text-center mt-8">
                  {search ? `No videos matching "${search}"` : 'No videos found.'}
                </p>
              )}
              {filteredVideos.map((v) => (
                <button
                  key={v.id}
                  onClick={() => {
                    onVideoSelect(`Tell me about the video: "${v.title}"`);
                    onClose();
                  }}
                  className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-[var(--bg-hover)] transition-colors group"
                >
                  <p className="text-xs text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] line-clamp-2 leading-snug">
                    {v.title}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-[var(--text-muted)]">{v.channel}</span>
                    {v.duration && (
                      <span className="text-[10px] text-[var(--text-dim)]">{formatDuration(v.duration)}</span>
                    )}
                  </div>
                </button>
              ))}

              {/* Load more */}
              {!search && hasMore && (
                <button
                  onClick={loadMoreVideos}
                  disabled={loadingMore}
                  className="w-full py-2.5 text-[10px] text-[var(--text-dim)] hover:text-[var(--text-muted)] transition-colors disabled:opacity-40"
                >
                  {loadingMore ? 'Loading...' : `Load more (${videos.length} of ${total})`}
                </button>
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
