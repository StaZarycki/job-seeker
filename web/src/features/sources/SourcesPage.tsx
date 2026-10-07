import { useMemo, useState } from 'react';

import {
  useCancelSync,
  useCategories,
  useSearches,
  useSources,
  useStartSync,
  useSyncHistory,
  useSyncStatus,
} from '../../api/hooks';
import { ApiErrorState } from '../../components/ApiErrorState';
import { RefreshIcon } from '../../components/icons';
import { Banner, ProgressBar, Skeleton } from '../../components/ui';
import { countLabel, durationSeconds, formatDateTime, formatNumber, OFFER_FORMS, plural } from '../../lib/format';
import s from './sources.module.css';

const SOURCE = 'justjoin';

export function SourcesPage() {
  const sources = useSources();
  const categories = useCategories(SOURCE);
  const searches = useSearches();
  const history = useSyncHistory();
  const syncStatus = useSyncStatus();
  const startSync = useStartSync();
  const cancelSync = useCancelSync();
  const [picked, setPicked] = useState<Set<string> | null>(null);
  // Until the user picks, preselect the categories used by the default search and all presets.
  const preselected = useMemo(
    () => new Set(searches.data?.flatMap((sum) => sum.preferences.categories) ?? []),
    [searches.data],
  );
  const selected = picked ?? preselected;

  const source = sources.data?.find((src) => src.name === SOURCE);
  const sync = syncStatus.data;
  const running = sync?.running ?? false;
  const count = selected.size;
  const progress = sync?.total ? Math.round((sync.fetched / sync.total) * 100) : null;

  return (
    <div>
      <header className={s.topbar}>
        <h1 className={s.title}>Źródła</h1>
        <span className={s.subtitle}>Serwisy z ofertami i synchronizacja lokalnej bazy</span>
      </header>
      <div className={`page ${s.grid}`}>
        {sources.error ? <ApiErrorState error={sources.error} onRetry={() => void sources.refetch()} /> : null}

        <section className="card" aria-label="JustJoin.it">
          <div className={s.sourceHead}>
            <h2 className={s.sourceName}>JustJoin.it</h2>
            <span className={source?.last_sync_error ? s.statusWarn : s.statusOk}>
              <span className={s.dot} />
              {source?.last_sync_error ? 'błąd' : 'działa'}
            </span>
            <span className={`mono muted ${s.apiName}`}>candidate-api</span>
          </div>

          <dl className={s.stats}>
            <div>
              <dt>Ofert w bazie</dt>
              <dd className={s.statBig}>{source ? formatNumber(source.offers_in_db) : '—'}</dd>
            </div>
            <div>
              <dt>Ostatnia synchronizacja</dt>
              <dd>{formatDateTime(source?.last_sync_finished)}</dd>
            </div>
            <div>
              <dt>Pobrano / nowych</dt>
              <dd>
                {source?.last_sync_fetched != null
                  ? `${formatNumber(source.last_sync_fetched)} / ${formatNumber(source.last_sync_new ?? 0)}`
                  : '—'}
              </dd>
            </div>
          </dl>
          {source?.last_sync_error ? <Banner tone="warn">{source.last_sync_error}</Banner> : null}

          <fieldset className={s.fieldset} disabled={running}>
            <legend className={s.legend}>Kategorie do pobrania</legend>
            <div className={s.cats}>
              {categories.data ? (
                categories.data.map((cat) => {
                  const on = selected.has(cat.key);
                  return (
                    <button
                      key={cat.key}
                      type="button"
                      aria-pressed={on}
                      aria-label={cat.count != null ? `${cat.key}, ${countLabel(cat.count, OFFER_FORMS)}` : cat.key}
                      className={`${s.cat} ${on ? s.catOn : ''}`}
                      onClick={() => {
                        const next = new Set(selected);
                        if (on) next.delete(cat.key);
                        else next.add(cat.key);
                        setPicked(next);
                      }}
                    >
                      <span className="mono">{cat.key}</span>
                      <span className={s.catCount}>{cat.count != null ? formatNumber(cat.count) : ''}</span>
                    </button>
                  );
                })
              ) : categories.error ? (
                <span className="muted">
                  Nie udało się pobrać listy kategorii: {(categories.error as Error).message}
                </span>
              ) : (
                Array.from({ length: 10 }, (_, i) => <Skeleton key={i} width={90} height={34} />)
              )}
            </div>
          </fieldset>

          {running && sync ? (
            <div className={s.progress} role="status">
              <div className={s.progressHead}>
                <span style={{ fontWeight: 500 }}>Pobieranie: {sync.category ?? '…'}</span>
                <span className="mono muted">
                  {sync.total ? `${formatNumber(sync.fetched)} / ${formatNumber(sync.total)}` : ''}
                </span>
              </div>
              <ProgressBar value={progress} label="Postęp synchronizacji" />
              <div className={s.progressFoot}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Kategoria {sync.category_index || 1} z {sync.category_count || count} · strony po 100 ofert
                </span>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => cancelSync.mutate()}
                  disabled={cancelSync.isPending}
                >
                  Przerwij
                </button>
              </div>
            </div>
          ) : (
            <div className={s.syncRow}>
              <button
                type="button"
                className={`btn btn-primary ${s.syncBtn}`}
                disabled={count === 0 || startSync.isPending}
                onClick={() => startSync.mutate({ categories: [...selected] })}
              >
                <RefreshIcon size={15} />
                Synchronizuj {count} {plural(count, ['kategorię', 'kategorie', 'kategorii'])}
              </button>
              <span className="muted" style={{ fontSize: 12.5 }}>
                ~20 s · oferty zapisywane bez filtrów, więc zmiana preferencji nie wymaga ponownej synchronizacji
              </span>
            </div>
          )}
          {sync && !running && sync.cancelled ? (
            <Banner>Synchronizacja przerwana – pobrane oferty zostały zapisane.</Banner>
          ) : null}
          {startSync.error ? <Banner tone="warn">{(startSync.error as Error).message}</Banner> : null}
        </section>

        <section className="card" aria-label="Historia synchronizacji">
          <h2 className={s.sourceName}>Historia synchronizacji</h2>
          {history.data?.length ? (
            <ul className={s.history}>
              {history.data.map((run) => (
                <li key={run.id} className={s.historyRow}>
                  <span className={`mono ${s.hStart}`}>{formatDateTime(run.started_at)}</span>
                  <span className={s.hCats}>
                    {run.categories === null ? '—' : run.categories.length ? run.categories.join(', ') : 'wszystkie'}
                    {run.error ? <span className={s.hError}> · {run.error}</span> : null}
                  </span>
                  <span className={`mono ${s.hNum} ${s.hFetched}`}>{formatNumber(run.fetched)}</span>
                  <span className={`mono ${s.hNum} ${s.hNew}`}>+{formatNumber(run.new)}</span>
                  <span className={`mono muted ${s.hNum} ${s.hTime}`}>
                    {durationSeconds(run.started_at, run.finished_at)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{history.isPending ? 'Wczytywanie…' : 'Jeszcze nie synchronizowano.'}</p>
          )}
          {history.data?.length ? (
            <p className="section-hint">
              {countLabel(history.data.length, ['synchronizacja', 'synchronizacje', 'synchronizacji'])} · kolumny:
              start, kategorie, pobrano, nowe, czas
            </p>
          ) : null}
        </section>

        <section className={`card ${s.future}`}>
          <h2 className={s.sourceName}>Kolejne serwisy</h2>
          <p className="muted" style={{ fontSize: 13 }}>
            Każdy serwis to osobny moduł w <span className="mono">backend/src/job_seeker/sources/</span> zarejestrowany
            w rejestrze źródeł. Po dodaniu pojawi się tutaj z własnym statusem i kategoriami.
          </p>
        </section>
      </div>
    </div>
  );
}
