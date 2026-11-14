// Client for the aRaaga service (../music-backend). Signed-in users carry a bearer token.
export const API_BASE = (import.meta.env.VITE_MUSIC_BASE_URL as string | undefined) ?? 'http://localhost:9100';

export interface Track {
  id: string; title: string; prompt: string; genre: string; language: string; raga: string; taal: string;
  mood: string; tempo_bpm: number; instruments: string[]; lyrics: string; duration_seconds: number;
  peaks: number[]; plays: number; likes: number; liked: boolean; audio_url: string; creator: string;
  created_at: string; visibility: string; brief_source: string; can_delete?: boolean;
}
export interface GenerateRequest {
  prompt: string; lyrics?: string; instrumental?: boolean; duration_seconds?: number; title?: string; public?: boolean; language?: string;
}
export type JobStatus = 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export interface Me { email: string; name: string; admin?: boolean }
const KEY = 'raaga-token';
export const getToken = (): string => { try { return localStorage.getItem(KEY) ?? ''; } catch { return ''; } };
export const setToken = (t: string) => { try { if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY); } catch { /* storage blocked */ } };

/** Dispatched on any 401 so the app can drop back to the sign-in page. */
export const SIGNED_OUT = 'raaga:signed-out';

async function call<T>(path: string, init: RequestInit = {}, authed = true): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    if (res.status === 401 && authed) { setToken(''); window.dispatchEvent(new Event(SIGNED_OUT)); }
    const body = await res.json().catch(() => ({}));
    const d = body.detail;
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? 'Please check the details you entered.' : `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const signUp = (name: string, email: string, password: string) =>
  call<{ token: string; user: Me }>('/api/auth/signup', { method: 'POST', body: JSON.stringify({ name, email, password }) }, false);
export const signIn = (email: string, password: string) =>
  call<{ token: string; user: Me }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }, false);
export const fetchMe = () => call<Me>('/api/auth/me');

export const audioSrc = (t: Track) => `${API_BASE}${t.audio_url}`;
export const listTracks = (p: Record<string, string>) =>
  call<{ tracks: Track[] }>(`/api/music/tracks?${new URLSearchParams(p)}`).then((r) => r.tracks);
export const generate = (b: GenerateRequest) => call<{ job_id: string }>('/api/music/generate', { method: 'POST', body: JSON.stringify(b) });
export const getJob = (id: string) => call<{ status: JobStatus; error?: string; track?: Track }>(`/api/music/jobs/${id}`);
export const toggleLike = (id: string) => call<Track>(`/api/music/tracks/${id}/like`, { method: 'POST' });
export const deleteTrack = (id: string) => call<{ deleted: string }>(`/api/music/tracks/${id}`, { method: 'DELETE' });
export const countPlay = (id: string) => call<Track>(`/api/music/tracks/${id}/play`, { method: 'POST' });

export interface CostRow { id: string; title: string; creator: string; language: string; created_at: string; duration_seconds: number; plays: number;
  polly_chars: number; polly_usd: number; llm_tokens_in: number; llm_tokens_out: number; llm_usd: number; compute_usd: number; create_usd: number;
  storage_usd_month: number; delivery_usd_to_date: number }
export interface Agg { songs: number; create_usd: number; polly_chars: number; llm_tokens: number; plays: number }
export interface Costs {
  songs: CostRow[]; by_creator: Record<string, Agg>; by_day: Record<string, Agg>;
  totals: { songs: number; create_usd: number; avg_create_usd: number; polly_chars: number; llm_tokens: number; storage_usd_month: number; delivery_usd_to_date: number };
  openrouter: { akanade_connected: boolean; raaga_tokens: number; raaga_usd: number; raaga_share_of_usage: number | null;
    account: null | { total_credits?: number; total_usage?: number; remaining?: number; error?: string } };
  prices: Record<string, unknown>;
}
export const fetchCosts = () => call<Costs>('/api/admin/costs');
