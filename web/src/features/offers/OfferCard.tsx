import { Link } from 'react-router';

import type { MatchResult } from '../../api/client';
import { BookmarkIcon, CheckIcon } from '../../components/icons';
import { CompanyLogo, ScoreBadge, SkillChips } from '../../components/ui';
import { citiesLabel, relativeDay, salaryText, workplaceLabel, years } from '../../lib/format';
import s from './offers.module.css';

function scoreSub(result: MatchResult): string {
  return result.ai ? `AI ${result.ai.assessment.score}` : '';
}

export function OfferCard({ result, href, selected }: { result: MatchResult; href: string; selected: boolean }) {
  const { offer, rule } = result;
  const salary = salaryText(offer);
  const visited = Boolean(result.visited_at || result.applied_at);
  return (
    <Link
      to={href}
      className={`${s.card} ${selected ? s.cardSelected : ''} ${visited ? s.cardVisited : ''}`}
      aria-current={selected ? 'true' : undefined}
    >
      <div className={s.cardScore}>
        <ScoreBadge score={result.final_score} sub={scoreSub(result)} />
      </div>
      <div className={s.cardBody}>
        <div className={s.cardTitle}>
          {result.status === 'saved' ? (
            <BookmarkIcon size={13} className={s.savedMark} aria-label="Zapisana" role="img" />
          ) : null}
          {offer.title}
        </div>
        <div className={s.cardMeta}>
          <span className={s.company}>
            <CompanyLogo src={offer.company_logo_url} company={offer.company} />
            {offer.company}
          </span>
          <span className={s.level}>{offer.seniority ?? '?'}</span>
          {result.applied_at ? (
            <span className={`${s.activityTag} ${s.activityApplied}`}>
              <CheckIcon size={11} />
              Aplikowano {relativeDay(result.applied_at)}
            </span>
          ) : result.visited_at ? (
            <span className={s.activityTag}>Odwiedzona {relativeDay(result.visited_at)}</span>
          ) : null}
          <span className="mono" style={{ fontSize: 11.5 }}>
            Ty: ~{years(rule.effective_years)} l.
          </span>
          <span>
            {workplaceLabel(offer.workplace_type)} · {citiesLabel(offer)}
          </span>
        </div>
        <SkillChips matched={rule.matched_skills} missing={rule.missing_skills} maxMatched={4} maxMissing={2} />
        <div className={s.cardSalaryInline}>
          <span className="mono">{salary ? salary.range : 'brak widełek'}</span>{' '}
          <span className="muted">{salary?.contract}</span>
        </div>
      </div>
      <div className={s.cardSalary}>
        <div className="mono" style={{ fontWeight: 500 }}>
          {salary ? salary.range : 'brak'}
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {salary ? salary.contract : 'widełek'}
        </div>
      </div>
    </Link>
  );
}
