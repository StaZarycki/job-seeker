import type { SearchSummary } from '../api/client';

export const DEFAULT_PRESET_LABEL = 'Domyślne';

export function presetLabel(name: string | null): string {
  return name ?? DEFAULT_PRESET_LABEL;
}

export function presetDescription(summary: SearchSummary): string {
  const prefs = summary.preferences;
  const parts: string[] = [];
  if (prefs.target_skills.length) parts.push(`Cel: ${prefs.target_skills.join(', ')}`);
  parts.push(prefs.categories.length ? prefs.categories.join(', ') : 'wszystkie kategorie');
  if (summary.needs_sync) parts.push('wymaga synchronizacji');
  return parts.join(' · ');
}
