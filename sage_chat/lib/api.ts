/**
 * lib/api.ts
 * Typed fetch functions for the Sage Chat FastAPI backend.
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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

export function getBudgetSpent(): number {
  try { return parseFloat(localStorage.getItem(BUDGET_KEY) ?? '0') || 0; } catch { return 0; }
}

export function addBudgetSpent(cost: number): number {
  const total = getBudgetSpent() + cost;
  try { localStorage.setItem(BUDGET_KEY, total.toFixed(6)); } catch {}
  return total;
}

// ── Chat storage ───────────────────────────────────────────────────────────

const CHATS_KEY = 'sage_chats';

export interface StoredChat {
  id: string;
  name: string;
  mode: 'ephemeral' | 'conversation';
  messages: any[]; // ChatMessage[] — avoid circular import
  savedAt: number;
}

// In-memory cache — avoids re-parsing localStorage on every save
let _chatsCache: StoredChat[] | null = null;

export function loadChats(): StoredChat[] {
  if (_chatsCache !== null) return _chatsCache;
  try {
    const raw = localStorage.getItem(CHATS_KEY);
    _chatsCache = raw ? JSON.parse(raw) : [];
    return _chatsCache!;
  } catch {
    _chatsCache = [];
    return [];
  }
}

export function saveChat(chat: StoredChat): void {
  try {
    const chats = loadChats().filter(c => c.id !== chat.id);
    chats.unshift(chat); // newest first
    _chatsCache = chats.slice(0, 50); // cap at 50
    localStorage.setItem(CHATS_KEY, JSON.stringify(_chatsCache));
  } catch {}
}

export function deleteChat(id: string): void {
  try {
    _chatsCache = loadChats().filter(c => c.id !== id);
    localStorage.setItem(CHATS_KEY, JSON.stringify(_chatsCache));
  } catch {}
}

export function renameChat(id: string, name: string): void {
  try {
    _chatsCache = loadChats().map(c => c.id === id ? { ...c, name } : c);
    localStorage.setItem(CHATS_KEY, JSON.stringify(_chatsCache));
  } catch {}
}

export function newChatId(): string {
  return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

// ── Helpers ────────────────────────────────────────────────────────────────

export function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${s}s`;
}
