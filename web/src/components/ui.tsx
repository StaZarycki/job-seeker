import { useState, type ReactNode } from 'react';

import type { RuleWeights } from '../lib/weights';
import { DEFAULT_WEIGHTS } from '../lib/weights';
import { scoreTone, type ScoreTone } from '../lib/format';
import { CheckIcon, CrossIcon, InfoIcon, WarningIcon } from './icons';
import s from './ui.module.css';

const toneClass: Record<ScoreTone, string> = { high: s.high!, mid: s.mid!, low: s.low! };

export function ScoreBadge({ score, sub, large = false }: { score: number; sub?: string; large?: boolean }) {
  const value = Math.round(score);
  return (
    <div className={`${s.score} ${large ? s.scoreLg : ''}`}>
      <div className={`${s.scoreValue} ${toneClass[scoreTone(value)]}`} aria-label={`Wynik ${value} na 100`}>
        {value}
      </div>
      {sub ? <div className={s.scoreSub}>{sub}</div> : null}
    </div>
  );
}

/** Company logo from the job board; the company's initial when there is none or it fails to load. */
export function CompanyLogo({ src, company, size = 18 }: { src: string | null; company: string; size?: number }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (!src || failedSrc === src) {
    return (
      <span
        className={s.logoFallback}
        style={{ width: size, height: size, fontSize: Math.round(size * 0.55) }}
        aria-hidden="true"
      >
        {company.trim().charAt(0).toUpperCase() || '?'}
      </span>
    );
  }
  // Fixed height, width follows the logo up to 3:1: about half the logos are wide wordmarks that a square would shrink.
  return (
    <img
      className={s.logo}
      src={src}
      alt=""
      height={size}
      style={{ height: size, minWidth: size, maxWidth: size * 3 }}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailedSrc(src)}
    />
  );
}

export function SkillChip({ name, matched }: { name: string; matched: boolean }) {
  return (
    <span className={`${s.chip} ${matched ? s.chipMatch : s.chipMiss}`}>
      {matched ? <CheckIcon size={11} /> : <CrossIcon size={11} />}
      <span className="visually-hidden">{matched ? 'masz:' : 'brakuje:'}</span>
      {name}
    </span>
  );
}

export function SkillChips({
  matched,
  missing,
  maxMatched = Infinity,
  maxMissing = Infinity,
}: {
  matched: string[];
  missing: string[];
  maxMatched?: number;
  maxMissing?: number;
}) {
  const shownMatched = matched.slice(0, maxMatched);
  const shownMissing = missing.slice(0, maxMissing);
  const rest = matched.length + missing.length - shownMatched.length - shownMissing.length;
  return (
    <div className={s.chips}>
      {shownMatched.map((name) => (
        <SkillChip key={`m-${name}`} name={name} matched />
      ))}
      {shownMissing.map((name) => (
        <SkillChip key={`x-${name}`} name={name} matched={false} />
      ))}
      {rest > 0 ? <span className={s.chipMore}>+{rest}</span> : null}
    </div>
  );
}

const BAR_LABELS: [keyof RuleWeights, string][] = [
  ['skills', 'Umiejętności'],
  ['title', 'Tytuł'],
  ['seniority', 'Seniority'],
  ['location', 'Lokalizacja'],
  ['salary', 'Widełki'],
  ['languages', 'Języki'],
  ['freshness', 'Świeżość'],
];

export function ScoreBars({
  breakdown,
  weights = DEFAULT_WEIGHTS,
}: {
  breakdown: Record<string, number>;
  weights?: RuleWeights;
}) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className={s.bars}>
      {BAR_LABELS.map(([key, label]) => {
        const pct = Math.round((breakdown[key] ?? 0) * 100);
        const fill = pct >= 80 ? s.fillHigh : pct >= 50 ? s.fillMid : s.fillLow;
        return (
          <div className={s.bar} key={key}>
            <span className={s.barLabel}>
              {label} <span className={s.barWeight}>{Math.round((weights[key] / total) * 100)}%</span>
            </span>
            <div
              className={s.track}
              role="meter"
              aria-label={label}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
            >
              <div className={`${s.fill} ${fill}`} style={{ width: `${pct}%` }} />
            </div>
            <span className={s.barValue}>{pct}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className={s.segmented} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          className={`${s.segment} ${value === option.value ? s.segmentActive : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Banner({
  tone = 'info',
  children,
  action,
  onDismiss,
}: {
  tone?: 'info' | 'warn';
  children: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
}) {
  return (
    <div className={`${s.banner} ${tone === 'warn' ? s.bannerWarn : ''}`} role="status">
      <span className={s.bannerIcon}>{tone === 'warn' ? <WarningIcon /> : <InfoIcon />}</span>
      <div className={s.bannerBody}>{children}</div>
      {action}
      {onDismiss ? (
        <button type="button" className={s.bannerClose} aria-label="Zamknij komunikat" onClick={onDismiss}>
          <CrossIcon size={14} strokeWidth={2} />
        </button>
      ) : null}
    </div>
  );
}

export function StateCard({
  tag,
  icon,
  title,
  children,
  actions,
}: {
  tag?: string;
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className={s.state} aria-label={title}>
      {tag ? <div className={s.stateTag}>{tag}</div> : null}
      {icon}
      <h2 className={s.stateTitle}>{title}</h2>
      {children ? <div className={s.stateText}>{children}</div> : null}
      {actions ? <div className={s.stateActions}>{actions}</div> : null}
    </section>
  );
}

export function Skeleton({ width = '100%', height = 10 }: { width?: string | number; height?: number }) {
  return <div className={s.skeleton} style={{ width, height }} aria-hidden="true" />;
}

export function ProgressBar({ value, label }: { value: number | null; label: string }) {
  return (
    <div
      className={s.progress}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value ?? undefined}
    >
      <div
        className={`${s.progressFill} ${value === null ? s.progressIndeterminate : ''}`}
        style={value === null ? undefined : { width: `${value}%` }}
      />
    </div>
  );
}
