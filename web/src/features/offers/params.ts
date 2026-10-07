import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

import type { MatchingMode, OfferStatus } from '../../api/client';
import type { MatchParams } from '../../api/hooks';

export const DEFAULT_TOP = 20;

export interface OfferFilters {
  search: string | null;
  mode: MatchingMode;
  top: number;
  category: string[];
  city: string[];
  minSalary: number | null;
  status: OfferStatus | null;
}

/** Offer list state lives in the URL (?search=cpp&mode=ai&category=c…) so views can be linked and go back. */
export function useOfferFilters(): [OfferFilters, (patch: Partial<OfferFilters>) => void] {
  const [params, setParams] = useSearchParams();

  const filters = useMemo<OfferFilters>(() => {
    const top = Number(params.get('top'));
    const minSalary = Number(params.get('min_salary'));
    const status = params.get('status');
    return {
      search: params.get('search'),
      mode: params.get('mode') === 'ai' ? 'ai' : 'basic',
      top: Number.isFinite(top) && top > 0 ? top : DEFAULT_TOP,
      category: params.getAll('category'),
      city: params.getAll('city'),
      minSalary: Number.isFinite(minSalary) && minSalary > 0 ? minSalary : null,
      status: status === 'saved' || status === 'hidden' ? status : null,
    };
  }, [params]);

  const update = useCallback(
    (patch: Partial<OfferFilters>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          const set = (key: string, value: string | number | null | undefined) => {
            if (value === null || value === undefined || value === '') next.delete(key);
            else next.set(key, String(value));
          };
          const setAll = (key: string, values: string[]) => {
            next.delete(key);
            values.forEach((v) => next.append(key, v));
          };
          if ('search' in patch) {
            set('search', patch.search);
            // Preset-specific overrides don't carry over to another preset.
            next.delete('category');
            next.delete('city');
            next.delete('min_salary');
          }
          if ('mode' in patch) set('mode', patch.mode === 'ai' ? 'ai' : null);
          if ('top' in patch) set('top', patch.top === DEFAULT_TOP ? null : patch.top);
          if (patch.category) setAll('category', patch.category);
          if (patch.city) setAll('city', patch.city);
          if ('minSalary' in patch) set('min_salary', patch.minSalary);
          if ('status' in patch) set('status', patch.status);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return [filters, update];
}

export function toMatchParams(filters: OfferFilters, mode: MatchingMode): MatchParams {
  return {
    search: filters.search,
    mode,
    top: filters.top,
    category: filters.category.length ? filters.category : undefined,
    city: filters.city.length ? filters.city : undefined,
    minSalary: filters.minSalary,
    status: filters.status,
  };
}
