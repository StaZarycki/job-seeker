import { useState } from 'react';
import { Link } from 'react-router';

import type { SearchSummary } from '../../api/client';
import { useSearches, useStartSync, useSyncStatus } from '../../api/hooks';
import { ApiErrorState } from '../../components/ApiErrorState';
import { ChevronDownIcon, ChevronUpIcon } from '../../components/icons';
import { presetLabel } from '../../lib/presets';
import { Skeleton } from '../../components/ui';
import { countLabel, formatNumber, OFFER_FORMS } from '../../lib/format';
import s from './searches.module.css';

const WORKPLACE: Record<string, string> = { remote: 'zdalnie', hybrid: 'hybrydowo', office: 'biuro' };

function rows(summary: SearchSummary): [string, string][] {
  const p = summary.preferences;
  return [
    ['Kategorie', p.categories.join(', ') || 'wszystkie'],
    ['Poziom', p.experience_levels === 'auto' ? 'auto' : p.experience_levels.join(', ')],
    ['Tryb pracy', p.workplace.map((w) => WORKPLACE[w] ?? w).join(', ')],
    ['Miasta', p.preferred_cities.join(', ') || '—'],
    ['Słowa w tytule', p.title_keywords.join(', ') || '—'],
    ['Wykluczone', p.exclude_keywords.join(', ') || '—'],
    ['Cel', p.target_skills.join(', ') || '—'],
  ];
}

function description(summary: SearchSummary): string {
  if (summary.name === null) return 'Sekcja [search] w config.toml';
  const target = summary.preferences.target_skills;
  return target.length
    ? `Przejście na ${target.join(', ')}`
    : `Kategorie: ${summary.preferences.categories.join(', ')}`;
}

function stats(summary: SearchSummary): string {
  if (summary.needs_sync) return 'nie zsynchronizowano';
  return `${countLabel(summary.considered, OFFER_FORMS)} · ${formatNumber(summary.passed)} po filtrach`;
}

export function SearchesPage() {
  const searches = useSearches();
  const syncStatus = useSyncStatus();
  const startSync = useStartSync();
  const [open, setOpen] = useState<string | null | undefined>(undefined);
  const syncing = syncStatus.data?.running ?? false;

  return (
    <div>
      <header className={s.topbar}>
        <h1 className={s.title}>Wyszukiwania</h1>
        <span className={s.subtitle}>
          Profile wyszukiwania z config.toml – każdy nadpisuje wybrane pola ustawień domyślnych.
        </span>
      </header>
      <div className={`page ${s.grid}`}>
        {searches.error ? <ApiErrorState error={searches.error} onRetry={() => void searches.refetch()} /> : null}
        {searches.isPending
          ? Array.from({ length: 3 }, (_, i) => (
              <div className="card" key={i}>
                <Skeleton width="40%" height={14} />
                <Skeleton width="80%" />
                <Skeleton width="60%" />
              </div>
            ))
          : null}
        {searches.data?.map((summary) => {
          const key = summary.name ?? '__default';
          const expanded = open === undefined ? summary.name === null : open === key;
          const isDefault = summary.name === null;
          const query = summary.name ? `?search=${encodeURIComponent(summary.name)}` : '';
          return (
            <section key={key} className={`card ${s.preset} ${isDefault ? s.presetDefault : ''}`}>
              <button
                type="button"
                className={s.presetHead}
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : key)}
              >
                <span className={s.presetTitleBlock}>
                  <span className={s.presetName}>
                    {presetLabel(summary.name)}
                    {isDefault ? <span className={s.badge}>domyślne</span> : null}
                  </span>
                  <span className="muted" style={{ fontSize: 12.5 }}>
                    {description(summary)}
                  </span>
                  <span className={`mono muted ${s.statsPhone}`}>{stats(summary)}</span>
                </span>
                <span className={s.chevron}>
                  {expanded ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
                </span>
              </button>
              <div className={`${s.presetBody} ${expanded ? s.presetBodyOpen : ''}`}>
                <dl className={s.rows}>
                  {rows(summary).map(([k, v]) => (
                    <div key={k} className={s.row}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                <div className={s.footer}>
                  <span className={`mono muted ${s.statsDesktop}`}>{stats(summary)}</span>
                  <button
                    type="button"
                    className="btn"
                    disabled={syncing || startSync.isPending}
                    onClick={() => startSync.mutate({ search: summary.name })}
                  >
                    {syncing ? 'Synchronizuję…' : 'Synchronizuj'}
                  </button>
                  <Link to={`/${query}`} className="btn btn-primary">
                    Pokaż oferty
                  </Link>
                </div>
              </div>
            </section>
          );
        })}

        <section className={`card ${s.newPreset}`}>
          <h2 className="card-title">Nowy profil wyszukiwania</h2>
          <p className="muted" style={{ fontSize: 13 }}>
            Dodaj sekcję w <span className="mono">backend/config.toml</span> i odśwież stronę. Wszystkie pola są
            opcjonalne – brakujące dziedziczą z ustawień domyślnych.
          </p>
          <pre className={s.snippet}>
            {'[searches.go]\ncategories = ["go"]\ntarget_skills = ["Go"]\ntitle_keywords = ["golang", "backend"]'}
          </pre>
        </section>
      </div>
    </div>
  );
}
