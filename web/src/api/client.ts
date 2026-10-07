import type { components } from './schema';

export type Schemas = components['schemas'];
export type MatchResponse = Schemas['MatchResponse'];
export type MatchResult = Schemas['MatchResult'];
export type JobOffer = Schemas['JobOffer'];
export type RuleScore = Schemas['RuleScore'];
export type AIResult = Schemas['AIResult'];
export type ProfileResponse = Schemas['ProfileResponse'];
export type CandidateProfile = Schemas['CandidateProfile'];
export type ProfileOverrides = Schemas['ProfileOverrides-Output'];
export type ProfileOverridesInput = Schemas['ProfileOverrides-Input'];
export type SearchSummary = Schemas['SearchSummaryItem'];
export type SearchPreferences = Schemas['SearchPreferences'];
export type Settings = Schemas['Settings'];
export type SourceStatus = Schemas['SourceStatus'];
export type SyncStatus = Schemas['SyncStatus'];
export type SyncHistoryItem = Schemas['SyncHistoryItem'];
export type CategoryInfo = Schemas['CategoryInfo'];
export type Salary = Schemas['Salary'];
export type MatchingMode = Schemas['MatchingMode'];
export type OfferStatus = 'saved' | 'hidden';

/** Machine-readable error codes returned by the backend (see backend/src/job_seeker/api/app.py). */
export type ApiErrorCode =
  | 'cv_not_found'
  | 'offer_not_found'
  | 'ai_not_configured'
  | 'ai_failed'
  | 'source_unavailable'
  | 'sync_in_progress'
  | 'invalid_request'
  | 'network'
  | 'unknown';

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;

  constructor(status: number, code: ApiErrorCode, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** The Vite dev server proxies /api to the FastAPI backend (see vite.config.ts). */
export const API_BASE = '/api';

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

export function buildQuery(query: Query = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.append(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : '';
}

export async function request<T>(path: string, init: RequestInit & { query?: Query } = {}): Promise<T> {
  const { query, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}${buildQuery(query)}`, rest);
  } catch {
    throw new ApiError(0, 'network', 'Brak połączenia z serwerem API. Czy backend działa (uv run jobseeker serve)?');
  }
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = errorDetail(body) ?? `Błąd serwera (HTTP ${response.status}).`;
    const code = (isRecord(body) && typeof body.code === 'string' ? body.code : 'unknown') as ApiErrorCode;
    throw new ApiError(response.status, code, detail);
  }
  return body as T;
}

export function jsonBody(data: unknown): RequestInit {
  return { body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } };
}

function errorDetail(body: unknown): string | null {
  if (!isRecord(body)) return null;
  const { detail } = body;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return 'Niepoprawne dane w zapytaniu.';
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
