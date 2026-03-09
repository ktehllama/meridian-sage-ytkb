export interface Profile {
  id: string;
  name: string;
  createdAt: number;
}

interface ProfilesStore {
  profiles: Profile[];
  activeId: string;
}

const PROFILES_KEY = 'meridian_profiles';

const DEFAULT_PROFILE: Profile = { id: 'default', name: 'Default', createdAt: 0 };

function loadStore(): ProfilesStore {
  try {
    const raw = localStorage.getItem(PROFILES_KEY);
    if (raw) {
      const store = JSON.parse(raw) as ProfilesStore;
      // Ensure Default always exists
      if (!store.profiles.find(p => p.id === 'default')) {
        store.profiles.unshift(DEFAULT_PROFILE);
      }
      return store;
    }
  } catch {}
  return { profiles: [DEFAULT_PROFILE], activeId: 'default' };
}

function saveStore(store: ProfilesStore): void {
  try {
    localStorage.setItem(PROFILES_KEY, JSON.stringify(store));
  } catch {}
}

export function loadProfiles(): Profile[] {
  return loadStore().profiles;
}

export function getActiveProfile(): Profile {
  const store = loadStore();
  return store.profiles.find(p => p.id === store.activeId) ?? DEFAULT_PROFILE;
}

export function setActiveProfile(id: string): void {
  const store = loadStore();
  if (store.profiles.find(p => p.id === id)) {
    store.activeId = id;
    saveStore(store);
  }
}

export function addProfile(name: string): Profile {
  const store = loadStore();
  const profile: Profile = {
    id: `profile_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    name: name.trim() || 'New Profile',
    createdAt: Date.now(),
  };
  store.profiles.push(profile);
  saveStore(store);
  return profile;
}

export function deleteProfile(id: string): void {
  if (id === 'default') return; // cannot delete Default
  const store = loadStore();
  store.profiles = store.profiles.filter(p => p.id !== id);
  if (store.activeId === id) {
    store.activeId = 'default';
  }
  saveStore(store);
}

export function renameProfile(id: string, name: string): void {
  if (id === 'default') return; // cannot rename Default
  const store = loadStore();
  const profile = store.profiles.find(p => p.id === id);
  if (profile) {
    profile.name = name.trim() || profile.name;
    saveStore(store);
  }
}
