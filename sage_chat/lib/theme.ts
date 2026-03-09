export type Theme = 'dark' | 'light';

const THEME_KEY = 'meridian_theme';

export function getTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return stored === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {}
  applyTheme(theme);
}

export function applyTheme(theme: Theme): void {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme === 'light' ? 'light' : '';
  }
}
