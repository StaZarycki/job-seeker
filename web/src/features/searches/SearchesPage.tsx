import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import type { SearchSummary } from '../../api/client';
import { useConfig, useSearches, useStartSync, useSyncStatus } from '../../api/hooks';
import { ApiErrorState } from '../../components/ApiErrorState';
import { ChevronDownIcon, ChevronLeftIcon, ChevronUpIcon, PlusIcon } from '../../components/icons';
import { Skeleton, StateCard } from '../../components/ui';
import { countLabel, formatNumber, OFFER_FORMS } from '../../lib/format';
import { PHONE_QUERY, useMediaQuery } from '../../lib/hooks';
import { presetLabel } from '../../lib/presets';
import { overridesLabel, WORKPLACE_LABELS, type SearchKey } from '../../lib/searchFields';
import { SearchEditor } from './SearchEditor';
import s from './searches.module.css';

/** URL ids: /searches/default (the [search] section), /searches/new, /searches/<preset>. */
const DEFAULT_ID = 'default';
const NEW_ID = 'new';

function idOf(summary: SearchSummary): string {
  return summary.name ?? DEFAULT_ID;
}

function stats(summary: SearchSummary): string {
  if (summary.needs_sync) return 'nie zsynchronizowano';
  return `${countLabel(summary.considered, OFFER_FORMS)} · ${formatNumber(summary.passed)} po filtrach`;
}

function description(summary: SearchSummary): string {
  const target = summary.preferences.target_skills;
  const what = target.length ? `Cel: ${target.join(', ')}` : summary.preferences.categories.join(', ') || 'wszystkie';
  return summary.name === null ? what : `${what} · ${overridesLabel(summary.overridden.length)}`;
}

function rows(summary: SearchSummary): [string, string, boolean][] {
  const p = summary.preferences;
  const own = (key: SearchKey) => summary.overridden.includes(key);
  return [
    ['Kategorie', p.categories.join(', ') || 'wszystkie', own('categories')],
    ['Poziom', p.experience_levels === 'auto' ? 'auto' : p.experience_levels.join(', '), own('experience_levels')],
    ['Tryb pracy', p.workplace.map((w) => WORKPLACE_LABELS[w].toLowerCase()).join(', '), own('workplace')],
    ['Miasta', p.preferred_cities.join(', ') || '—', own('preferred_cities')],
    ['Słowa w tytule', p.title_keywords.join(', ') || '—', own('title_keywords')],
    ['Wykluczone', p.exclude_keywords.join(', ') || '—', own('exclude_keywords')],
    ['Cel', p.target_skills.join(', ') || '—', own('target_skills')],
  ];
}

export function SearchesPage() {
  const { name: param } = useParams();
  const phone = useMediaQuery(PHONE_QUERY);
  const navigate = useNavigate();
  const searches = useSearches();
  const config = useConfig();
  const selected = param ?? (phone ? undefined : DEFAULT_ID);

  const list = searches.data ?? [];
  const base = list.find((x) => x.name === null)?.preferences;
  const summary = selected === NEW_ID ? null : list.find((x) => idOf(x) === selected);
  const loading = searches.isPending || config.isPending;
  const error = searches.error ?? config.error;

  const editor =
    selected && base && config.data ? (
      summary === undefined ? (
        <StateCard
          tag="404"
          title="Nie ma takiego profilu wyszukiwania"
          actions={
            <Link to="/searches" className="btn">
              Wróć do listy
            </Link>
          }
        />
      ) : (
        <SearchEditor
          key={selected}
          summary={summary}
          base={base}
          version={config.data.version}
          takenNames={list.flatMap((x) => (x.name ? [x.name] : []))}
          stats={summary ? stats(summary) : undefined}
          header={
            phone ? (
              <div className={s.phoneBar}>
                <Link to="/searches" className={`btn btn-ghost ${s.back}`}>
                  <ChevronLeftIcon size={18} />
                  Wyszukiwania
                </Link>
                {summary ? <span className="mono muted">{stats(summary)}</span> : null}
              </div>
            ) : null
          }
          onSaved={(name) => navigate(`/searches/${encodeURIComponent(name ?? DEFAULT_ID)}`, { replace: true })}
          onDeleted={() => navigate('/searches', { replace: true })}
          onReload={() => {
            void config.refetch();
            void searches.refetch();
          }}
        />
      )
    ) : null;

  if (phone && selected) {
    return <div className={s.phoneEditor}>{error ? <ApiErrorState error={error} /> : (editor ?? <Loading />)}</div>;
  }

  return (
    <div>
      <header className={s.topbar}>
        <div className={s.titleBlock}>
          <h1 className={s.title}>Wyszukiwania</h1>
          <span className={s.subtitle}>Ustawienia domyślne i profile wyszukiwania · zapisywane w config.toml</span>
        </div>
        {phone ? (
          <Link to={`/searches/${NEW_ID}`} className="icon-btn" aria-label="Nowy profil wyszukiwania">
            <PlusIcon size={18} />
          </Link>
        ) : (
          <Link to={`/searches/${NEW_ID}`} className={`btn ${s.newBtn}`}>
            <PlusIcon size={15} />
            Nowy profil
          </Link>
        )}
      </header>
      <div className={`page ${s.layout}`}>
        {error ? <ApiErrorState error={error} onRetry={() => void searches.refetch()} /> : null}
        {loading && !error ? <Loading /> : null}
        {phone ? (
          <PhoneList list={list} />
        ) : (
          <>
            <nav className={s.list} aria-label="Lista wyszukiwań">
              {list.map((item) => {
                const id = idOf(item);
                return (
                  <Link
                    key={id}
                    to={`/searches/${encodeURIComponent(id)}`}
                    aria-current={id === selected ? 'page' : undefined}
                    className={`${s.listItem} ${id === selected ? s.listItemOn : ''}`}
                  >
                    <span className={s.listName}>
                      {presetLabel(item.name)}
                      {item.name === null ? <span className={s.badge}>bazowe</span> : null}
                    </span>
                    <span className="muted" style={{ fontSize: 12.5 }}>
                      {description(item)}
                    </span>
                    <span className="mono muted" style={{ fontSize: 11.5 }}>
                      {stats(item)}
                    </span>
                  </Link>
                );
              })}
              {selected === NEW_ID ? (
                <span className={`${s.listItem} ${s.listItemOn}`} aria-current="page">
                  <span className={s.listName}>nowy profil</span>
                  <span className="muted" style={{ fontSize: 12.5 }}>
                    Niezapisany
                  </span>
                </span>
              ) : null}
              <p className="muted" style={{ fontSize: 12, margin: '4px 2px 0' }}>
                Profil nadpisuje tylko wybrane pola. Reszta dziedziczy z Domyślnych, więc zmiana tam działa we
                wszystkich profilach.
              </p>
            </nav>
            <div className={s.editorColumn}>{editor}</div>
          </>
        )}
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div className="card">
      <Skeleton width="40%" height={14} />
      <Skeleton width="80%" />
      <Skeleton width="60%" />
    </div>
  );
}

/** Phone: expandable summaries; editing opens /searches/<name> full screen. */
function PhoneList({ list }: { list: SearchSummary[] }) {
  const [open, setOpen] = useState<string | null | undefined>(undefined);
  const syncStatus = useSyncStatus();
  const startSync = useStartSync();
  const syncing = syncStatus.data?.running ?? false;
  return (
    <>
      {list.map((summary) => {
        const id = idOf(summary);
        const expanded = open === undefined ? summary.name === null : open === id;
        return (
          <section key={id} className={`card ${s.preset} ${expanded ? s.presetOpen : ''}`}>
            <button
              type="button"
              className={s.presetHead}
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : id)}
            >
              <span className={s.presetText}>
                <span className={s.listName}>
                  {presetLabel(summary.name)}
                  {summary.name === null ? <span className={s.badge}>bazowe</span> : null}
                </span>
                <span className="muted" style={{ fontSize: 12.5 }}>
                  {description(summary)}
                </span>
                <span className="mono muted" style={{ fontSize: 11.5 }}>
                  {stats(summary)}
                </span>
              </span>
              {expanded ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
            </button>
            {expanded ? (
              <div className={s.presetBody}>
                <dl className={s.rows}>
                  {rows(summary).map(([k, v, own]) => (
                    <div key={k} className={s.row}>
                      <dt>{k}</dt>
                      <dd className={own ? s.own : ''}>{v}</dd>
                    </div>
                  ))}
                </dl>
                {summary.name ? (
                  <span className="muted" style={{ fontSize: 11.5 }}>
                    Na niebiesko pola nadpisane w tym profilu, reszta z Domyślnych.
                  </span>
                ) : null}
                <div className={s.presetActions}>
                  <Link to={`/searches/${encodeURIComponent(id)}`} className="btn">
                    Edytuj
                  </Link>
                  <button
                    type="button"
                    className="btn"
                    disabled={syncing || startSync.isPending}
                    onClick={() => startSync.mutate({ search: summary.name })}
                  >
                    Synchronizuj
                  </button>
                  <Link
                    to={summary.name ? `/?search=${encodeURIComponent(summary.name)}` : '/'}
                    className="btn btn-primary"
                  >
                    Oferty
                  </Link>
                </div>
              </div>
            ) : null}
          </section>
        );
      })}
      <p className="muted" style={{ fontSize: 12, margin: '0 2px' }}>
        Profil nadpisuje tylko wybrane pola. Reszta dziedziczy z Domyślnych, więc zmiana tam działa we wszystkich
        profilach.
      </p>
    </>
  );
}
