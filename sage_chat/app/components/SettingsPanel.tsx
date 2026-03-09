'use client';

import { useState, useEffect } from 'react';
import { Theme, getTheme, setTheme } from '../../lib/theme';
import { Profile, loadProfiles, getActiveProfile, setActiveProfile, addProfile, deleteProfile, renameProfile } from '../../lib/profiles';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const [theme, setThemeState] = useState<Theme>('dark');
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeId, setActiveId] = useState('default');
  const [addingProfile, setAddingProfile] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setThemeState(getTheme());
    setProfiles(loadProfiles());
    setActiveId(getActiveProfile().id);
  }, [isOpen]);

  const handleThemeToggle = (t: Theme) => {
    setTheme(t);
    setThemeState(t);
  };

  const handleSetActive = (id: string) => {
    setActiveProfile(id);
    setActiveId(id);
  };

  const handleAddProfile = () => {
    if (!newProfileName.trim()) return;
    addProfile(newProfileName.trim());
    setProfiles(loadProfiles());
    setNewProfileName('');
    setAddingProfile(false);
  };

  const handleDelete = (id: string) => {
    deleteProfile(id);
    setProfiles(loadProfiles());
    if (activeId === id) setActiveId('default');
  };

  const handleRename = (id: string) => {
    renameProfile(id, editingName.trim() || id);
    setProfiles(loadProfiles());
    setEditingId(null);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 z-30" onClick={onClose} />

      {/* Drawer — slides in from right */}
      <aside className="fixed right-0 top-0 h-full w-72 bg-[var(--bg-sidebar)] border-l border-[var(--border-primary)] z-40 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-[var(--border-primary)]">
          <span className="font-semibold text-sm text-[var(--text-primary)]">Settings</span>
          <button
            onClick={onClose}
            className="text-[var(--text-dim)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* ── Appearance ── */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-dim)] mb-3">Appearance</h3>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--text-secondary)]">Theme</span>
              <div
                className="flex items-center rounded-full p-0.5 w-[9rem]"
                style={{ background: 'rgba(101,112,252,0.08)', border: '1px solid rgba(101,112,252,0.18)' }}
              >
                {(['dark', 'light'] as Theme[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => handleThemeToggle(t)}
                    className={`flex-1 text-[11px] font-medium py-1 rounded-full capitalize transition-all ${
                      theme === t
                        ? 'text-[var(--text-primary)] bg-[rgba(101,112,252,0.3)]'
                        : 'text-[var(--text-dim)] hover:text-[var(--text-muted)]'
                    }`}
                    style={theme === t ? { textShadow: '0 0 8px rgba(101,112,252,0.8)' } : {}}
                  >
                    {t === 'dark' ? 'Dark' : 'Light'}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* ── Profiles ── */}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-dim)] mb-3">Profiles</h3>

            <div className="space-y-1">
              {profiles.map((p) => {
                const isActive = p.id === activeId;
                const isEditing = editingId === p.id;
                return (
                  <div
                    key={p.id}
                    className={`group relative flex items-center gap-2 rounded-lg px-3 py-2 border transition-all ${
                      isActive
                        ? 'bg-indigo-600/10 border-indigo-500/30'
                        : 'bg-[var(--bg-elevated)] border-[var(--border-primary)] hover:border-[var(--border-subtle)]'
                    }`}
                  >
                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isActive ? 'bg-indigo-400' : 'bg-[var(--text-faintest)]'}`} />

                    {isEditing ? (
                      <input
                        autoFocus
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRename(p.id);
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        onBlur={() => handleRename(p.id)}
                        className="flex-1 bg-[var(--bg-hover)] border border-indigo-500/40 rounded px-2 py-0.5 text-xs text-[var(--text-primary)] focus:outline-none"
                      />
                    ) : (
                      <button
                        className="flex-1 text-left text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                        onClick={() => handleSetActive(p.id)}
                      >
                        {p.name}
                      </button>
                    )}

                    {p.id !== 'default' && !isEditing && (
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => { setEditingId(p.id); setEditingName(p.name); }}
                          className="p-0.5 text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors"
                          title="Rename"
                        >
                          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDelete(p.id)}
                          className="p-0.5 text-[var(--text-faint)] hover:text-red-400 transition-colors"
                          title="Delete"
                        >
                          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                            <path d="M10 11v6M14 11v6"/>
                          </svg>
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {addingProfile ? (
              <div className="mt-2 flex gap-2">
                <input
                  autoFocus
                  value={newProfileName}
                  onChange={(e) => setNewProfileName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddProfile();
                    if (e.key === 'Escape') { setAddingProfile(false); setNewProfileName(''); }
                  }}
                  onBlur={() => { if (!newProfileName.trim()) { setAddingProfile(false); setNewProfileName(''); } }}
                  placeholder="Profile name..."
                  className="flex-1 bg-[var(--bg-hover)] border border-indigo-500/40 rounded px-2 py-1 text-xs text-[var(--text-primary)] placeholder-[var(--text-faint)] focus:outline-none"
                />
                <button
                  onClick={handleAddProfile}
                  className="px-2 py-1 text-xs text-indigo-400 border border-indigo-500/40 rounded hover:bg-indigo-500/10 transition-colors"
                >
                  Add
                </button>
              </div>
            ) : (
              <button
                onClick={() => setAddingProfile(true)}
                className="mt-2 w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-dashed border-[var(--border-primary)] text-xs text-[var(--text-dim)] hover:border-indigo-500/40 hover:text-indigo-400 transition-all"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                Add profile
              </button>
            )}

            {/* Coming soon note */}
            <div className="mt-4 p-3 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-primary)]">
              <p className="text-[10px] text-[var(--text-faint)] leading-relaxed">
                <span className="text-indigo-400/70 font-medium">Coming soon —</span>{' '}
                each profile will have its own personal knowledge base, separate from the shared DB.
                Add any video to your profile without affecting others.
              </p>
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}
