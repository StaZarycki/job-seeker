import { http, HttpResponse } from 'msw';

import type {
  CandidateProfile,
  JobOffer,
  MatchResponse,
  MatchResult,
  ProfileOverrides,
  ProfileResponse,
  SearchPreferences,
  SearchSummary,
  Settings,
  SourceStatus,
  SyncStatus,
} from '../api/client';

export const preferences: SearchPreferences = {
  sources: ['justjoin'],
  categories: ['javascript', 'python'],
  experience_levels: 'auto',
  workplace: ['remote', 'hybrid'],
  preferred_cities: ['Katowice', 'Kraków'],
  onsite_only_in_preferred_cities: true,
  min_salary_pln_month: null,
  exclude_keywords: ['Java'],
  title_keywords: ['backend'],
  avoid_title_keywords: [],
  target_skills: [],
  max_offer_age_days: 45,
};

export function offer(id: string, title: string, overrides: Partial<JobOffer> = {}): JobOffer {
  return {
    id: `justjoin:${id}`,
    source: 'justjoin',
    external_id: id,
    url: `https://justjoin.it/job-offer/${id}`,
    title,
    company: 'ACME',
    category: 'javascript',
    seniority: 'mid',
    workplace_type: 'remote',
    working_time: 'full_time',
    locations: [{ city: 'Warszawa', street: null }],
    required_skills: [{ name: 'Node.js', level: 4 }],
    nice_to_have_skills: [],
    languages: [],
    salaries: [
      {
        contract: 'b2b',
        min_pln_month: 20000,
        max_pln_month: 25000,
        gross: false,
        original_currency: 'PLN',
        original_unit: 'month',
        original_min: null,
        original_max: null,
      },
    ],
    published_at: '2026-10-07T10:00:00Z',
    expires_at: null,
    apply_url: null,
    company_logo_url: null,
    description: null,
    extra: { slug: id },
    ...overrides,
  };
}

export function result(o: JobOffer, score: number, extra: Partial<MatchResult> = {}): MatchResult {
  return {
    offer: o,
    rule: {
      score,
      breakdown: { skills: 0.9, title: 1, seniority: 1, location: 1, salary: 0.8, languages: 1, freshness: 1 },
      matched_skills: ['Node.js'],
      missing_skills: ['Kubernetes'],
      notes: ['Praca zdalna'],
      effective_years: 3.4,
      effective_level: 'mid',
      main_skills: ['Node.js'],
    },
    ai: null,
    final_score: score,
    status: null,
    visited_at: null,
    applied_at: null,
    ...extra,
  };
}

export const RESULTS = [
  result(offer('a1', 'Backend Engineer'), 92),
  result(offer('b2', 'Senior Node.js Developer', { seniority: 'senior' }), 81),
];

export function matchResponse(results: MatchResult[] = RESULTS, extra: Partial<MatchResponse> = {}): MatchResponse {
  return {
    mode: 'basic',
    considered: 100,
    filtered_out: 60,
    passed: 40,
    profile_hash: 'abc',
    profile_rebuilt: false,
    warning: null,
    preferences,
    ai: null,
    results,
    ...extra,
  };
}

export const profile: CandidateProfile = {
  parser_version: 2,
  source_file: 'cv.pdf',
  source_hash: 'h',
  built_at: '2026-10-07T10:00:00Z',
  headline: 'Software Developer',
  location: 'Katowice, Poland',
  years_of_experience: 4,
  seniority: 'mid',
  skills: [
    { name: 'node.js', weight: 1 },
    { name: 'python', weight: 1 },
    { name: 'docker', weight: 0.75 },
  ],
  skill_years: { 'node.js': 3 },
  languages: { pl: 'C2', en: 'C1' },
  cv_text: '',
};

export const profileResponse: ProfileResponse = { profile, profile_hash: 'abc', rebuilt: false, warning: null };

export const emptyOverrides: ProfileOverrides = {
  add_skills: [],
  remove_skills: [],
  skill_weights: {},
  skill_years: {},
  years_of_experience: null,
  seniority: null,
  languages: {},
  extra_notes: null,
};

export const settings: Settings = {
  default_mode: 'basic',
  weights: { skills: 0.45, title: 0.1, seniority: 0.15, location: 0.1, salary: 0.1, languages: 0.05, freshness: 0.05 },
  experience: { transfer_ratio: 0.35, declared_ratio: 0.5 },
  ai: { provider: 'anthropic', model: 'claude-haiku-4-5', top_n: 20, weight: 0.7 },
};

export const searches: SearchSummary[] = [
  { name: null, preferences, considered: 100, passed: 40, needs_sync: false },
  {
    name: 'cpp',
    preferences: { ...preferences, categories: ['c'], target_skills: ['C++'] },
    considered: 20,
    passed: 5,
    needs_sync: false,
  },
  {
    name: 'python',
    preferences: { ...preferences, categories: ['python'] },
    considered: 0,
    passed: 0,
    needs_sync: true,
  },
];

export const sources: SourceStatus[] = [
  {
    name: 'justjoin',
    offers_in_db: 2619,
    last_sync_started: '2026-10-07T19:36:00Z',
    last_sync_finished: '2026-10-07T19:36:18Z',
    last_sync_fetched: 2447,
    last_sync_new: 2,
    last_sync_error: null,
  },
];

export const idleSync: SyncStatus = {
  running: false,
  started_at: null,
  finished_at: null,
  source: null,
  category: null,
  category_index: 0,
  category_count: 0,
  fetched: 0,
  total: null,
  cancelled: false,
  error: null,
  results: [],
};

/** Handlers for everything the app shell and pages load besides the thing a test is about. */
export function baseHandlers() {
  return [
    http.get('/api/profile', () => HttpResponse.json(profileResponse)),
    http.get('/api/profile/overrides', () => HttpResponse.json(emptyOverrides)),
    http.get('/api/settings', () => HttpResponse.json(settings)),
    http.get('/api/searches', () => HttpResponse.json(searches)),
    http.get('/api/sources', () => HttpResponse.json(sources)),
    http.get('/api/sync/status', () => HttpResponse.json(idleSync)),
    http.get('/api/syncs', () => HttpResponse.json([])),
    http.get('/api/sources/justjoin/categories', () =>
      HttpResponse.json([
        { key: 'javascript', count: 712 },
        { key: 'python', count: 965 },
        { key: 'c', count: 301 },
      ]),
    ),
    http.get('/api/offers/:id', ({ params }) =>
      HttpResponse.json({ ...offer(String(params.id).split(':')[1] ?? 'x', 'X'), description: 'Opis oferty' }),
    ),
  ];
}
