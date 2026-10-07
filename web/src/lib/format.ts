import type { JobOffer, Salary } from '../api/client';

/** 25713 -> "25 713" (plain spaces, as in the design). */
export function formatNumber(value: number): string {
  return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

const CONTRACTS: Record<string, string> = {
  b2b: 'B2B',
  permanent: 'UoP',
  mandate_contract: 'UZ',
  internship: 'staż',
  any: 'dowolna',
};

export function contractLabel(salary: Salary): string {
  const label = CONTRACTS[salary.contract] ?? salary.contract;
  return salary.gross && salary.contract !== 'b2b' ? `${label}, brutto` : label;
}

/** The salary entry with the highest upper bound (mirrors JobOffer.best_salary in the backend). */
export function bestSalary(offer: JobOffer): Salary | null {
  let best: Salary | null = null;
  for (const salary of offer.salaries) {
    const value = salary.max_pln_month ?? salary.min_pln_month;
    if (value == null) continue;
    const bestValue = best ? (best.max_pln_month ?? best.min_pln_month ?? 0) : -1;
    if (value > bestValue) best = salary;
  }
  return best;
}

export interface SalaryText {
  range: string;
  contract: string;
}

export function salaryText(offer: JobOffer): SalaryText | null {
  const salary = bestSalary(offer);
  if (!salary) return null;
  const low = salary.min_pln_month != null ? formatNumber(salary.min_pln_month) : '?';
  const high = salary.max_pln_month != null ? formatNumber(salary.max_pln_month) : '?';
  return { range: `${low} – ${high}`, contract: contractLabel(salary) };
}

/** Polish plural forms: plural(5, ['oferta', 'oferty', 'ofert']) -> "ofert". */
export function plural(n: number, [one, few, many]: [string, string, string]): string {
  if (n === 1) return one;
  const lastDigit = n % 10;
  const lastTwo = n % 100;
  return lastDigit >= 2 && lastDigit <= 4 && (lastTwo < 12 || lastTwo > 14) ? few : many;
}

export function countLabel(n: number, forms: [string, string, string]): string {
  return `${formatNumber(n)} ${plural(n, forms)}`;
}

export const OFFER_FORMS: [string, string, string] = ['oferta', 'oferty', 'ofert'];

/** "2026-10-07T19:36:32Z" -> "7.10, 21:36" in the user's time zone. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  const day = `${date.getDate()}.${date.getMonth() + 1}`;
  const time = date.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
  return `${day}, ${time}`;
}

export function durationSeconds(start: string | null | undefined, end: string | null | undefined): string {
  if (!start || !end) return '—';
  const seconds = Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000));
  return `${seconds} s`;
}

const WORKPLACE: Record<string, string> = { remote: 'Zdalnie', hybrid: 'Hybrydowo', office: 'Stacjonarnie' };

export function workplaceLabel(value: string | null | undefined): string {
  return value ? (WORKPLACE[value] ?? value) : '—';
}

export function citiesLabel(offer: JobOffer, max = 3): string {
  const cities = [...new Set(offer.locations.map((l) => l.city))];
  if (cities.length <= max) return cities.join(', ');
  return `${cities.slice(0, max).join(', ')} +${cities.length - max}`;
}

/** 2.9 -> "2.9", 4 -> "4" (years are shown with one decimal like in the design). */
export function years(value: number | null | undefined): string {
  if (value == null) return '?';
  return String(Math.round(value * 10) / 10);
}

export type ScoreTone = 'high' | 'mid' | 'low';

export function scoreTone(score: number): ScoreTone {
  if (score >= 80) return 'high';
  if (score >= 60) return 'mid';
  return 'low';
}

export function percent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}
