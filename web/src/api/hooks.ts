import { useEffect, useRef } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  ApiError,
  jsonBody,
  request,
  type CategoryInfo,
  type JobOffer,
  type MatchResponse,
  type MatchResult,
  type MatchingMode,
  type ActivityFilter,
  type OfferActivity,
  type OfferStatus,
  type ProfileOverrides,
  type ProfileOverridesInput,
  type ProfileResponse,
  type SearchSummary,
  type Settings,
  type SourceStatus,
  type SyncHistoryItem,
  type SyncStatus,
} from './client';

export interface MatchParams {
  search: string | null;
  mode: MatchingMode;
  top: number;
  category?: string[];
  city?: string[];
  minSalary?: number | null;
  status?: OfferStatus | null;
  activity?: ActivityFilter | null;
}

export const keys = {
  matches: (p: MatchParams) => ['matches', p] as const,
  allMatches: ['matches'] as const,
  offer: (id: string) => ['offer', id] as const,
  profile: ['profile'] as const,
  overrides: ['overrides'] as const,
  searches: ['searches'] as const,
  settings: ['settings'] as const,
  sources: ['sources'] as const,
  categories: (source: string) => ['categories', source] as const,
  syncStatus: ['sync-status'] as const,
  syncs: ['syncs'] as const,
};

/** Don't retry client errors (missing CV, missing AI key, unknown preset) - they won't fix themselves. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function useMatches(params: MatchParams, enabled = true) {
  return useQuery({
    queryKey: keys.matches(params),
    queryFn: () =>
      request<MatchResponse>('/matches', {
        query: {
          search: params.search,
          mode: params.mode,
          top: params.top,
          category: params.category,
          city: params.city,
          min_salary: params.minSalary,
          status: params.status,
          activity: params.activity,
        },
      }),
    enabled,
    placeholderData: params.mode === 'basic' ? keepPreviousData : undefined,
    staleTime: 60_000,
  });
}

export function useOffer(offerId: string | undefined) {
  return useQuery({
    queryKey: keys.offer(offerId ?? ''),
    queryFn: () => request<JobOffer>(`/offers/${encodeURIComponent(offerId ?? '')}`),
    enabled: Boolean(offerId),
    staleTime: Infinity,
  });
}

export function useProfile() {
  return useQuery({ queryKey: keys.profile, queryFn: () => request<ProfileResponse>('/profile') });
}

export function useOverrides() {
  return useQuery({ queryKey: keys.overrides, queryFn: () => request<ProfileOverrides>('/profile/overrides') });
}

export function useSearches() {
  return useQuery({ queryKey: keys.searches, queryFn: () => request<SearchSummary[]>('/searches'), staleTime: 60_000 });
}

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: () => request<Settings>('/settings'), staleTime: Infinity });
}

export function useSources() {
  return useQuery({ queryKey: keys.sources, queryFn: () => request<SourceStatus[]>('/sources') });
}

export function useCategories(source: string) {
  return useQuery({
    queryKey: keys.categories(source),
    queryFn: () => request<CategoryInfo[]>(`/sources/${source}/categories`),
    staleTime: 10 * 60_000,
  });
}

export function useSyncHistory() {
  return useQuery({
    queryKey: keys.syncs,
    queryFn: () => request<SyncHistoryItem[]>('/syncs', { query: { limit: 10 } }),
  });
}

/** Sync progress; polls while a sync runs and refreshes offer data once it finishes. */
export function useSyncStatus() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: keys.syncStatus,
    queryFn: () => request<SyncStatus>('/sync/status'),
    refetchInterval: (q) => (q.state.data?.running ? 700 : false),
  });
  const wasRunning = useRef(false);
  const running = query.data?.running ?? false;
  useEffect(() => {
    if (wasRunning.current && !running) {
      for (const key of [keys.allMatches, keys.sources, keys.syncs, keys.searches]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    }
    wasRunning.current = running;
  }, [running, queryClient]);
  return query;
}

export function useStartSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { search?: string | null; categories?: string[] | null }) =>
      request<SyncStatus>('/sync', { method: 'POST', ...jsonBody(body) }),
    onSuccess: (status) => queryClient.setQueryData(keys.syncStatus, status),
  });
}

export function useCancelSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => request<void>('/sync', { method: 'DELETE' }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.syncStatus }),
  });
}

export function useSetOfferStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, status }: { offerId: string; status: OfferStatus | null }) =>
      request<void>(`/offers/${encodeURIComponent(offerId)}/status`, { method: 'PUT', ...jsonBody({ status }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.allMatches }),
  });
}

/** Visited / applied marks. The cached lists are patched right away so the card dims as soon as the link is clicked. */
export function useSetOfferActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ offerId, ...update }: { offerId: string; visited?: boolean; applied?: boolean }) =>
      request<OfferActivity>(`/offers/${encodeURIComponent(offerId)}/activity`, { method: 'PUT', ...jsonBody(update) }),
    onMutate: ({ offerId, visited, applied }) => {
      const now = new Date().toISOString();
      const patch = (result: MatchResult): MatchResult => {
        if (result.offer.id !== offerId) return result;
        let { visited_at, applied_at } = result;
        if (visited === false) visited_at = applied_at = null;
        else if (visited) visited_at = now;
        if (applied) {
          visited_at ??= now;
          applied_at ??= now;
        } else if (applied === false) applied_at = null;
        return { ...result, visited_at, applied_at };
      };
      queryClient.setQueriesData<MatchResponse>({ queryKey: keys.allMatches }, (data) =>
        data ? { ...data, results: data.results.map(patch) } : data,
      );
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.allMatches }),
  });
}

export function useAssessOffer() {
  return useMutation({
    mutationFn: ({ offerId, search }: { offerId: string; search: string | null }) =>
      request<MatchResult>(`/offers/${encodeURIComponent(offerId)}/assess`, { method: 'POST', query: { search } }),
  });
}

function useProfileMutation<TArg>(fn: (arg: TArg) => Promise<ProfileResponse>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (profile) => {
      queryClient.setQueryData(keys.profile, profile);
      for (const key of [keys.allMatches, keys.searches, keys.overrides]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export function useUploadCv() {
  return useProfileMutation((file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<ProfileResponse>('/profile/cv', { method: 'POST', body: form });
  });
}

export function useRebuildProfile() {
  return useProfileMutation(() => request<ProfileResponse>('/profile/rebuild', { method: 'POST' }));
}

export function useSaveOverrides() {
  return useProfileMutation((overrides: ProfileOverridesInput) =>
    request<ProfileResponse>('/profile/overrides', { method: 'PUT', ...jsonBody(overrides) }),
  );
}
