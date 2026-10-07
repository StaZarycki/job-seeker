import type { ReactNode } from 'react';

import { ApiError, type MatchResult } from '../../api/client';
import { useAssessOffer, useOffer, useSetOfferActivity, useSetOfferStatus, useSettings } from '../../api/hooks';
import {
  BookmarkIcon,
  CheckIcon,
  ChevronLeftIcon,
  CrossIcon,
  ExternalIcon,
  EyeOffIcon,
  SparkleIcon,
} from '../../components/icons';
import { CompanyLogo, ScoreBars, ScoreBadge, Skeleton, SkillChips } from '../../components/ui';
import { citiesLabel, percent, relativeDay, salaryText, workplaceLabel, years } from '../../lib/format';
import { PHONE_QUERY, useMediaQuery } from '../../lib/hooks';
import s from './offers.module.css';

export function OfferDetail({
  result,
  aiMode,
  aiTopN,
  search,
  position,
  onClose,
  onHidden,
  onAssessed,
}: {
  result: MatchResult;
  aiMode: boolean;
  aiTopN: number;
  search: string | null;
  position?: string;
  onClose?: () => void;
  onHidden: () => void;
  onAssessed: (result: MatchResult) => void;
}) {
  const { offer, rule, ai } = result;
  const settings = useSettings();
  const phone = useMediaQuery(PHONE_QUERY);
  const details = useOffer(offer.description ? undefined : offer.id);
  const setStatus = useSetOfferStatus();
  const setActivity = useSetOfferActivity();
  const assess = useAssessOffer();
  const description = offer.description ?? details.data?.description ?? null;
  const salary = salaryText(offer);
  const transfer = settings.data ? percent(settings.data.experience.transfer_ratio) : '35%';
  const saved = result.status === 'saved';
  // The effective-experience note is shown as its own explanation below; the location/salary ones stay.
  const notes = rule.notes.filter((note) => !note.startsWith('Doświadczenie w technologiach oferty'));

  const toggleSaved = () => setStatus.mutate({ offerId: offer.id, status: saved ? null : 'saved' });
  const markVisited = () => setActivity.mutate({ offerId: offer.id, visited: true });
  const toggleApplied = () => setActivity.mutate({ offerId: offer.id, applied: !result.applied_at });
  const hide = () => setStatus.mutate({ offerId: offer.id, status: 'hidden' }, { onSuccess: onHidden });
  const runAssessment = () =>
    assess.mutate({ offerId: offer.id, search }, { onSuccess: (assessed) => onAssessed(assessed) });

  let aiBlock: ReactNode;
  if (ai) {
    const a = ai.assessment;
    aiBlock = (
      <section className={s.aiBlock} aria-label="Ocena AI">
        <div className={s.aiHeader}>
          <SparkleIcon size={15} />
          Ocena AI
          <span className={s.aiModel}>
            {ai.model} · {a.score}/100
          </span>
        </div>
        <p>{a.summary}</p>
        <ul className={s.proCon}>
          {a.pros.map((p) => (
            <li key={`p-${p}`}>
              <span className={s.pro} aria-hidden="true">
                +
              </span>
              <span>
                <span className="visually-hidden">Plus: </span>
                {p}
              </span>
            </li>
          ))}
          {a.cons.map((c) => (
            <li key={`c-${c}`}>
              <span className={s.con} aria-hidden="true">
                −
              </span>
              <span>
                <span className="visually-hidden">Minus: </span>
                {c}
              </span>
            </li>
          ))}
        </ul>
      </section>
    );
  } else if (aiMode) {
    aiBlock = (
      <div className={s.aiPrompt}>
        <span>Oferta poza top {aiTopN} ocenianych przez AI – pokazany wynik Standard.</span>
        <button type="button" className="btn" onClick={runAssessment} disabled={assess.isPending}>
          <SparkleIcon size={14} />
          {assess.isPending ? 'Oceniam…' : 'Oceń tę ofertę'}
        </button>
        {assess.error ? <span className={s.inlineError}>{(assess.error as ApiError).message}</span> : null}
      </div>
    );
  } else {
    aiBlock = (
      <div className={s.aiPrompt}>
        <span>Tryb Standard jest darmowy. Model AI może ocenić tę ofertę i wypisać plusy, minusy i braki.</span>
        <button type="button" className="btn" onClick={runAssessment} disabled={assess.isPending}>
          <SparkleIcon size={14} />
          {assess.isPending ? 'Oceniam…' : 'Oceń przez AI'}
        </button>
        {assess.error ? <span className={s.inlineError}>{(assess.error as ApiError).message}</span> : null}
      </div>
    );
  }

  const applyHref = offer.apply_url || offer.url;
  const saveButton = (
    <button
      type="button"
      className={`btn ${saved ? s.savedBtn : ''}`}
      aria-pressed={saved}
      onClick={toggleSaved}
      disabled={setStatus.isPending}
    >
      <BookmarkIcon size={15} />
      {saved ? 'Zapisano' : 'Zapisz'}
    </button>
  );
  const applyLink = (
    <a
      href={applyHref}
      target="_blank"
      rel="noreferrer"
      className={`btn btn-primary ${s.applyBtn}`}
      onClick={markVisited}
      onAuxClick={(event) => {
        if (event.button === 1) markVisited();
      }}
    >
      Aplikuj w JustJoin.it
      <ExternalIcon size={14} />
    </a>
  );

  return (
    <article className={s.detail} aria-label={`Oferta: ${offer.title}`}>
      <header className={s.detailBar}>
        {onClose ? (
          <button type="button" className={`btn btn-ghost ${s.backBtn}`} onClick={onClose}>
            <ChevronLeftIcon size={18} />
            Oferty
          </button>
        ) : null}
        {position ? <span className={`mono muted ${s.position}`}>{position}</span> : null}
        <button
          type="button"
          className={`icon-btn ${s.hideBtn}`}
          aria-label="Ukryj ofertę"
          title="Ukryj ofertę"
          onClick={hide}
        >
          <EyeOffIcon size={17} />
        </button>
        {onClose ? (
          <button type="button" className={`icon-btn ${s.closeBtn}`} aria-label="Zamknij szczegóły" onClick={onClose}>
            <CrossIcon size={15} strokeWidth={2} />
          </button>
        ) : null}
      </header>

      <div className={s.detailScroll}>
        <div className={s.detailHead}>
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <h2 className={s.detailTitle}>{offer.title}</h2>
            <div className={`muted ${s.detailCompany}`}>
              <CompanyLogo src={offer.company_logo_url} company={offer.company} size={20} />
              {offer.company}
            </div>
          </div>
          <ScoreBadge
            score={result.final_score}
            large
            sub={ai ? `AI ${ai.assessment.score} · Standard ${Math.round(rule.score)}` : 'tryb Standard'}
          />
        </div>

        {phone ? null : (
          <div className={s.detailActionsInline}>
            {applyLink}
            {saveButton}
            <button type="button" className="btn btn-ghost" onClick={hide} disabled={setStatus.isPending}>
              Ukryj
            </button>
          </div>
        )}

        <div className={s.activityRow}>
          <span className={s.activityText}>
            {result.visited_at ? (
              <>
                Odwiedzona {relativeDay(result.visited_at)}
                <button
                  type="button"
                  className={s.linkBtn}
                  aria-label="Oznacz jako nieodwiedzoną"
                  onClick={() => setActivity.mutate({ offerId: offer.id, visited: false })}
                >
                  Cofnij
                </button>
              </>
            ) : (
              'Jeszcze nie otwierana w JustJoin.it'
            )}
          </span>
          <button
            type="button"
            className={`btn ${s.appliedBtn} ${result.applied_at ? s.appliedOn : ''}`}
            aria-pressed={Boolean(result.applied_at)}
            onClick={toggleApplied}
          >
            <CheckIcon size={14} />
            {result.applied_at ? `Aplikowano ${relativeDay(result.applied_at)}` : 'Oznacz jako aplikowaną'}
          </button>
        </div>

        <dl className={s.metaGrid}>
          <div>
            <dt>Poziom oferty</dt>
            <dd>{offer.seniority ?? '—'}</dd>
          </div>
          <div>
            <dt>Twoje doświadczenie</dt>
            <dd>
              ~{years(rule.effective_years)} lat · {rule.effective_level ?? '?'}
            </dd>
          </div>
          <div>
            <dt>Tryb pracy</dt>
            <dd>
              {workplaceLabel(offer.workplace_type)} · {citiesLabel(offer)}
            </dd>
          </div>
          <div>
            <dt>Widełki (PLN/mies.)</dt>
            <dd className="mono">{salary ? `${salary.range} · ${salary.contract}` : 'brak widełek'}</dd>
          </div>
        </dl>

        {aiBlock}

        <section className={s.detailSection} aria-label="Wynik Standard">
          <h3 className={s.sectionTitle}>
            Wynik Standard <span className="mono muted">{Math.round(rule.score)}/100</span>
          </h3>
          <ScoreBars breakdown={rule.breakdown} weights={settings.data?.weights} />
        </section>

        <section className={s.detailSection} aria-label="Umiejętności">
          <h3 className={s.sectionTitle}>Umiejętności</h3>
          <SkillChips matched={rule.matched_skills} missing={ai ? ai.assessment.missing_skills : rule.missing_skills} />
          <div className="note">
            Doświadczenie w technologiach oferty ({rule.main_skills.join(', ') || 'tej roli'}): ~
            {years(rule.effective_years)} roku → poziom {rule.effective_level ?? '?'}. Liczone z pozycji w CV; ogólny
            staż przenosi się w {transfer}.
          </div>
          {notes.length ? (
            <ul className={s.notes}>
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className={s.detailSection} aria-label="Opis">
          <h3 className={s.sectionTitle}>Opis</h3>
          {description ? (
            <p className={s.description}>{description}</p>
          ) : details.isError ? (
            <p className="muted">Nie udało się pobrać opisu. Otwórz ofertę w JustJoin.it.</p>
          ) : (
            <div className={s.descSkeleton} aria-label="Pobieranie opisu">
              <Skeleton width="92%" />
              <Skeleton width="78%" />
              <Skeleton width="85%" />
              <span className="muted" style={{ fontSize: 12 }}>
                Pobieranie opisu z JustJoin.it…
              </span>
            </div>
          )}
        </section>
      </div>

      {phone ? (
        <footer className={s.detailFooter}>
          {saveButton}
          {applyLink}
        </footer>
      ) : null}
    </article>
  );
}
