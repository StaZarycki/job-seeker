import { useCallback, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';

import { ApiError, type MatchResponse, type MatchResult } from '../../api/client';
import { useMatches, useSearches, useSettings, useSources, useStartSync, useSyncStatus } from '../../api/hooks';
import { ApiErrorState } from '../../components/ApiErrorState';
import { DatabaseIcon, RefreshIcon, SparkleIcon } from '../../components/icons';
import { PresetPicker } from '../../components/PresetPicker';
import { Banner, ProgressBar, Segmented, Skeleton, StateCard } from '../../components/ui';
import { countLabel, formatDateTime, formatNumber, OFFER_FORMS, plural } from '../../lib/format';
import { useEscape, useMediaQuery, WIDE_QUERY } from '../../lib/hooks';
import { FilterChips } from './FilterChips';
import { OfferCard } from './OfferCard';
import { OfferDetail } from './OfferDetail';
import s from './offers.module.css';
import { toMatchParams, useOfferFilters } from './params';

export function OffersPage() {
  const { offerId } = useParams();
  const { search: query } = useLocation();
  const navigate = useNavigate();
  const wide = useMediaQuery(WIDE_QUERY);
  const [filters, setFilters] = useOfferFilters();
  const [assessed, setAssessed] = useState<Record<string, MatchResult>>({});

  const settings = useSettings();
  const searches = useSearches();
  const sources = useSources();
  const syncStatus = useSyncStatus();
  const startSync = useStartSync();

  const basic = useMatches(toMatchParams(filters, 'basic'));
  const ai = useMatches(toMatchParams(filters, 'ai'), filters.mode === 'ai');
  const aiError = filters.mode === 'ai' && ai.error instanceof ApiError ? ai.error : null;
  const report: MatchResponse | undefined = (filters.mode === 'ai' ? ai.data : undefined) ?? basic.data;
  const aiPending = filters.mode === 'ai' && ai.isFetching && !ai.data;

  const results = useMemo(() => (report?.results ?? []).map((r) => assessed[r.offer.id] ?? r), [report, assessed]);
  const selectedId = offerId ? decodeURIComponent(offerId) : wide ? results[0]?.offer.id : undefined;
  const selected = results.find((r) => r.offer.id === selectedId);
  const selectedIndex = selected ? results.indexOf(selected) : -1;

  const listHref = `/${query}`;
  const closeDetail = useCallback(() => navigate(listHref), [navigate, listHref]);
  useEscape(Boolean(offerId) && !wide, closeDetail);

  const onHidden = () => {
    const next = results[selectedIndex + 1] ?? results[selectedIndex - 1];
    navigate(wide && next ? `/offers/${encodeURIComponent(next.offer.id)}${query}` : listHref);
  };

  const source = sources.data?.[0];
  const sync = syncStatus.data;
  const syncing = sync?.running ?? false;

  if (basic.error && !basic.data) {
    return (
      <main className="page">
        <PageTitle />
        <ApiErrorState error={basic.error} onRetry={() => void basic.refetch()} />
      </main>
    );
  }

  const emptyDb = source && source.offers_in_db === 0;
  const noResults = report && report.results.length === 0;

  return (
    <div className={s.layout}>
      <header className={s.topbar}>
        <h1 className={s.pageTitle}>Oferty</h1>
        <div className={s.controls}>
          <PresetPicker
            value={filters.search}
            searches={searches.data ?? []}
            onChange={(name) => setFilters({ search: name })}
          />
          <Segmented
            label="Tryb oceny"
            value={filters.mode}
            options={[
              { value: 'basic', label: 'Standard' },
              { value: 'ai', label: 'AI' },
            ]}
            onChange={(mode) => setFilters({ mode })}
          />
        </div>
        <div className={s.syncInfo}>
          {syncing && sync ? (
            <span className={`mono ${s.syncText}`} role="status">
              Synchronizacja: {sync.category ?? '…'}{' '}
              {sync.total ? `${formatNumber(sync.fetched)} / ${formatNumber(sync.total)}` : ''}
            </span>
          ) : source ? (
            <span className={`mono muted ${s.syncText}`}>
              <span className={s.hidePhone}>JustJoin.it · </span>
              {formatDateTime(source.last_sync_finished)}
              <span className={s.hidePhone}> · {countLabel(source.offers_in_db, OFFER_FORMS)}</span>
            </span>
          ) : null}
          <button
            type="button"
            className={`btn ${s.syncBtn}`}
            disabled={syncing || startSync.isPending}
            onClick={() => startSync.mutate({ search: filters.search })}
            aria-label="Synchronizuj oferty"
          >
            <RefreshIcon size={15} />
            <span className={s.hidePhone}>{syncing ? 'Synchronizuję…' : 'Synchronizuj'}</span>
          </button>
        </div>
      </header>

      <div className={s.main}>
        {report ? <FilterChips prefs={report.preferences} filters={filters} onChange={setFilters} /> : null}

        {report?.warning ? (
          <Banner
            tone="warn"
            action={
              <Link to="/profile" className="btn">
                Wgraj CV
              </Link>
            }
          >
            {report.warning}
          </Banner>
        ) : null}
        {report?.profile_rebuilt ? (
          <Banner>Profil przebudowany z nowego CV – oceny AI zostaną policzone od nowa.</Banner>
        ) : null}
        {startSync.error ? <Banner tone="warn">{(startSync.error as Error).message}</Banner> : null}
        {sync && !sync.running && sync.error && !sync.cancelled ? (
          <Banner tone="warn">Synchronizacja nie powiodła się: {sync.error}</Banner>
        ) : null}

        {aiError ? (
          <Banner
            tone="warn"
            action={
              <button type="button" className="btn" onClick={() => setFilters({ mode: 'basic' })}>
                Wróć do trybu Standard
              </button>
            }
          >
            {aiError.code === 'ai_not_configured' ? <strong>Tryb AI nie jest skonfigurowany. </strong> : null}
            {aiError.message}
          </Banner>
        ) : null}
        {report?.ai && report.ai.failed > 0 ? (
          <Banner tone="warn">
            <strong>
              Model nie ocenił {report.ai.failed} z {report.ai.failed + report.ai.calls + report.ai.cached}{' '}
              {plural(report.ai.failed + report.ai.calls + report.ai.cached, OFFER_FORMS)}.
            </strong>{' '}
            {report.ai.errors[0]}
          </Banner>
        ) : null}
        {aiPending ? (
          <div className={s.aiProgress} role="status">
            <div className={s.aiProgressHead}>
              <SparkleIcon size={15} />
              <strong>Ocena AI w toku</strong>
              <span className="mono muted">
                {settings.data?.ai.model} · do {settings.data?.ai.top_n ?? 20} ofert · ranking Standard widoczny od razu
              </span>
            </div>
            <ProgressBar value={null} label="Ocena AI w toku" />
          </div>
        ) : null}

        {report ? (
          <div className={s.summary}>
            <span>
              <span className={s.summaryValue}>{formatNumber(report.passed)}</span> z {formatNumber(report.considered)}{' '}
              {OFFER_FORMS[2]} po filtrach
            </span>
            <span>
              pokazano <span className={s.summaryValue}>{report.results.length}</span>
            </span>
            {report.ai ? (
              <span className={s.summaryAi}>
                <SparkleIcon size={13} />
                {report.ai.model} · {report.ai.calls + report.ai.cached} ocen · {report.ai.cached} z cache
                {report.ai.failed ? ` · ${report.ai.failed} błędów` : ''}
              </span>
            ) : null}
          </div>
        ) : null}

        {emptyDb ? (
          <StateCard
            tag="brak ofert"
            icon={<DatabaseIcon size={34} strokeWidth={1.5} style={{ color: 'var(--muted)' }} />}
            title="Baza ofert jest pusta"
            actions={
              <button
                type="button"
                className="btn btn-primary"
                disabled={syncing}
                onClick={() => startSync.mutate({ search: filters.search })}
              >
                Synchronizuj teraz
              </button>
            }
          >
            Pobierz oferty z JustJoin.it, żeby zobaczyć ranking dopasowany do CV.
          </StateCard>
        ) : noResults ? (
          <StateCard tag="0 wyników" title="Żadna oferta nie przeszła filtrów">
            {filters.status === 'saved'
              ? 'Nie masz jeszcze zapisanych ofert w tym wyszukiwaniu.'
              : filters.activity === 'applied'
                ? 'Żadna oferta w tym wyszukiwaniu nie jest oznaczona jako aplikowana.'
                : filters.activity === 'unvisited'
                  ? 'Wszystkie pasujące oferty były już otwierane w JustJoin.it.'
                  : `Odrzucono ${formatNumber(report.filtered_out)} z ${formatNumber(report.considered)} ofert. Poluzuj filtry powyżej albo w config.toml.`}
          </StateCard>
        ) : (
          <div className={s.split}>
            <section className={s.list} aria-label="Ranking ofert" aria-busy={basic.isFetching}>
              {report
                ? results.map((r) => (
                    <OfferCard
                      key={r.offer.id}
                      result={r}
                      href={`/offers/${encodeURIComponent(r.offer.id)}${query}`}
                      selected={r.offer.id === selectedId}
                    />
                  ))
                : Array.from({ length: 6 }, (_, i) => <CardSkeleton key={i} />)}
            </section>

            {selected ? (
              <>
                {!wide ? (
                  <button
                    type="button"
                    className={s.drawerBackdrop}
                    aria-label="Zamknij szczegóły"
                    onClick={closeDetail}
                  />
                ) : null}
                <aside className={`${s.detailPane} ${wide ? '' : s.detailOverlay}`}>
                  <OfferDetail
                    key={selected.offer.id}
                    result={selected}
                    aiMode={filters.mode === 'ai'}
                    aiTopN={settings.data?.ai.top_n ?? 20}
                    search={filters.search}
                    position={`${selectedIndex + 1} / ${results.length}`}
                    onClose={wide ? undefined : closeDetail}
                    onHidden={onHidden}
                    onAssessed={(r) => setAssessed((a) => ({ ...a, [r.offer.id]: r }))}
                  />
                </aside>
              </>
            ) : offerId && report ? (
              <aside className={`${s.detailPane} ${wide ? '' : s.detailOverlay}`}>
                <StateCard
                  title="Oferty nie ma na tej liście"
                  actions={
                    <Link to={listHref} className="btn">
                      Wróć do ofert
                    </Link>
                  }
                >
                  Mogła zostać ukryta, wygasnąć albo nie przejść filtrów aktualnego wyszukiwania.
                </StateCard>
              </aside>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function PageTitle() {
  return <h1 className={s.pageTitle}>Oferty</h1>;
}

function CardSkeleton() {
  return (
    <div className={s.card} aria-hidden="true">
      <div className={s.cardScore}>
        <Skeleton width={40} height={24} />
      </div>
      <div className={s.cardBody}>
        <Skeleton width="70%" height={12} />
        <Skeleton width="45%" />
        <Skeleton width="55%" />
      </div>
    </div>
  );
}
