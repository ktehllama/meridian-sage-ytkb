/**
 * lib/api.ts
 * Typed fetch functions for the Sage Chat FastAPI backend.
 */

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined'
    ? window.location.protocol === 'https:'
      ? `https://${window.location.hostname}`   // behind nginx — /api/ proxied on 443
      : `http://${window.location.hostname}:8000` // direct to uvicorn over HTTP
    : 'http://localhost:8000')
).replace(/\/$/, '');

if (typeof window !== 'undefined') {
  console.log('[Meridian] API_URL:', API_URL);
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface Source {
  src_id: string;
  title: string;
  timestamp_str: string;
  url: string;
  quote: string;
}

export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  mode: 'ephemeral' | 'conversation';
  usage?: UsageInfo;
}

export interface VideoItem {
  id: string;
  title: string;
  channel: string;
  url: string;
  duration: number | null;
}

export interface VideoListResponse {
  videos: VideoItem[];
  total: number;
}

export interface ChannelItem {
  name: string;
  video_count: number;
}

export interface ChannelListResponse {
  channels: ChannelItem[];
}

export interface HealthResponse {
  status: string;
  chroma_chunks: number;
  db_videos: number;
  model: string;
}

// ── API functions ──────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // ignore parse error
    }
    console.error('[Meridian] API error:', response.status, response.url, detail);
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export async function chat(
  query: string,
  mode: 'ephemeral' | 'conversation',
  history: Message[],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, mode, history }),
    signal,
  });
  return handleResponse<ChatResponse>(response);
}

export async function getVideos(
  channel?: string,
  limit = 50,
  offset = 0,
): Promise<VideoListResponse> {
  const params = new URLSearchParams();
  if (channel) params.set('channel', channel);
  params.set('limit', String(limit));
  params.set('offset', String(offset));

  const response = await fetch(`${API_URL}/api/videos?${params}`);
  return handleResponse<VideoListResponse>(response);
}

export async function getChannels(): Promise<ChannelListResponse> {
  const response = await fetch(`${API_URL}/api/channels`);
  return handleResponse<ChannelListResponse>(response);
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health`);
  return handleResponse<HealthResponse>(response);
}

export interface RandomFact {
  title: string;
  channel: string;
  excerpt: string;
  timestamp_str: string;
  url: string;
}

export async function getRandomFact(): Promise<RandomFact> {
  const response = await fetch(`${API_URL}/api/random-fact`);
  return handleResponse<RandomFact>(response);
}

// ── Cost tracking ──────────────────────────────────────────────────────────

// Gemini 2.0 Flash Vertex AI pricing (as of 2025)
const PRICE_INPUT_PER_TOKEN = 0.075 / 1_000_000;   // $0.075 per 1M input tokens
const PRICE_OUTPUT_PER_TOKEN = 0.30 / 1_000_000;   // $0.30 per 1M output tokens

export function calcCost(usage: UsageInfo): number {
  return (
    usage.prompt_tokens * PRICE_INPUT_PER_TOKEN +
    usage.completion_tokens * PRICE_OUTPUT_PER_TOKEN
  );
}

const BUDGET_KEY = 'sage_budget_spent';
const BUDGET_CAP_KEY = 'sage_budget_cap';
const DEFAULT_BUDGET = 300;

let _budgetSpent: number | null = null;

export async function initBudgetFromServer(): Promise<void> {
  try {
    const res = await fetch(`${API_URL}/api/budget`);
    if (!res.ok) return;
    const data = await res.json();
    // Budget is monotonically increasing — take the higher value.
    // If local has more spending history than server (e.g. server was reset),
    // push local to server so it becomes the new source of truth.
    let local = 0;
    try { local = parseFloat(localStorage.getItem(BUDGET_KEY) ?? '0') || 0; } catch {}
    if (local > data.spent) {
      _budgetSpent = local;
      fetch(`${API_URL}/api/budget`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spent: local }),
      }).catch(() => {});
    } else {
      _budgetSpent = data.spent;
      try { localStorage.setItem(BUDGET_KEY, data.spent.toFixed(6)); } catch {}
    }
  } catch {}
}

export function getBudgetSpent(): number {
  if (_budgetSpent !== null) return _budgetSpent;
  try { return parseFloat(localStorage.getItem(BUDGET_KEY) ?? '0') || 0; } catch { return 0; }
}

export function addBudgetSpent(cost: number): number {
  const total = getBudgetSpent() + cost;
  _budgetSpent = total;
  try { localStorage.setItem(BUDGET_KEY, total.toFixed(6)); } catch {}
  fetch(`${API_URL}/api/budget`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spent: total }),
  }).catch(() => {});
  return total;
}

export function getBudgetCap(): number {
  try { return parseFloat(localStorage.getItem(BUDGET_CAP_KEY) ?? String(DEFAULT_BUDGET)) || DEFAULT_BUDGET; } catch { return DEFAULT_BUDGET; }
}

export function setBudgetCap(cap: number): void {
  try { localStorage.setItem(BUDGET_CAP_KEY, cap.toFixed(5)); } catch {}
}

// ── Chat storage ───────────────────────────────────────────────────────────

export interface StoredChat {
  id: string;
  name: string;
  mode: 'ephemeral' | 'conversation';
  messages: any[]; // ChatMessage[] — avoid circular import
  savedAt: number;
}

// In-memory cache — populated from server on initChatsFromServer()
let _chatsCache: StoredChat[] | null = null;

export function loadChats(): StoredChat[] {
  return _chatsCache ?? [];
}

export async function initChatsFromServer(): Promise<void> {
  try {
    const response = await fetch(`${API_URL}/api/chats`);
    if (response.ok) {
      _chatsCache = await response.json();
    }
  } catch {
    // server unreachable — cache stays empty, app still usable
  }
}

export function saveChat(chat: StoredChat): void {
  const chats = (_chatsCache ?? []).filter(c => c.id !== chat.id);
  chats.unshift(chat);
  _chatsCache = chats.slice(0, 50);
  fetch(`${API_URL}/api/chats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...chat, saved_at: chat.savedAt }),
  }).catch(() => {});
}

export function deleteChat(id: string): void {
  _chatsCache = (_chatsCache ?? []).filter(c => c.id !== id);
  fetch(`${API_URL}/api/chats/${id}`, { method: 'DELETE' }).catch(() => {});
}

export function renameChat(id: string, name: string): void {
  _chatsCache = (_chatsCache ?? []).map(c => c.id === id ? { ...c, name } : c);
  fetch(`${API_URL}/api/chats/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }).catch(() => {});
}

export function newChatId(): string {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

// ── Helpers ────────────────────────────────────────────────────────────────

export function formatModelName(modelId: string): string {
  // "gemini-2.0-flash" → "Gemini 2.0 Flash"
  // "gemini-2.5-flash-preview-05-20" → "Gemini 2.5 Flash"
  return modelId
    .replace(/-preview.*$/, '')          // strip -preview-... suffix
    .split('-')
    .map(p => p.charAt(0).toUpperCase() + p.slice(1))
    .join(' ');
}

export function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s}s`;
}
