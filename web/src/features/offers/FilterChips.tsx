import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';

import type { SearchPreferences } from '../../api/client';
import { ChevronDownIcon } from '../../components/icons';
import { formatNumber } from '../../lib/format';
import { useEscape } from '../../lib/hooks';
import { DEFAULT_TOP, type OfferFilters } from './params';
import s from './offers.module.css';

function splitList(value: string): string[] {
  return value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);
}

interface EditableChip {
  key: string;
  label: string;
  value: string;
  input: string;
  inputLabel: string;
  inputMode?: 'numeric' | 'text';
  placeholder?: string;
  modified: boolean;
  apply: (value: string) => void;
  reset: () => void;
}

/** Filter chips: the search's preferences; categories, cities, salary and top N can be overridden ad hoc. */
export function FilterChips({
  prefs,
  filters,
  onChange,
}: {
  prefs: SearchPreferences;
  filters: OfferFilters;
  onChange: (patch: Partial<OfferFilters>) => void;
}) {
  const categories = filters.category.length ? filters.category : prefs.categories;
  const cities = filters.city.length ? filters.city : prefs.preferred_cities;
  const minSalary = filters.minSalary ?? prefs.min_salary_pln_month;

  const editable: EditableChip[] = [
    {
      key: 'category',
      label: 'Kategorie',
      value: categories.join(', ') || 'wszystkie',
      input: categories.join(', '),
      inputLabel: 'Kategorie (po przecinku)',
      placeholder: 'np. javascript, python',
      modified: filters.category.length > 0,
      apply: (v) => onChange({ category: splitList(v) }),
      reset: () => onChange({ category: [] }),
    },
    {
      key: 'city',
      label: 'Miasta',
      value: cities.join(', ') || '—',
      input: cities.join(', '),
      inputLabel: 'Preferowane miasta (po przecinku)',
      placeholder: 'np. Katowice, Kraków',
      modified: filters.city.length > 0,
      apply: (v) => onChange({ city: splitList(v) }),
      reset: () => onChange({ city: [] }),
    },
    {
      key: 'salary',
      label: 'Min. widełki',
      value: minSalary ? `${formatNumber(minSalary)} PLN` : '—',
      input: minSalary ? String(minSalary) : '',
      inputLabel: 'Minimalne górne widełki (PLN/mies.)',
      inputMode: 'numeric',
      placeholder: 'np. 18000',
      modified: filters.minSalary !== null,
      apply: (v) => onChange({ minSalary: Number(v.replace(/\s/g, '')) || null }),
      reset: () => onChange({ minSalary: null }),
    },
    {
      key: 'top',
      label: 'Top',
      value: String(filters.top),
      input: String(filters.top),
      inputLabel: 'Liczba pokazywanych ofert',
      inputMode: 'numeric',
      modified: filters.top !== DEFAULT_TOP,
      apply: (v) => onChange({ top: Math.min(500, Math.max(1, Number(v) || DEFAULT_TOP)) }),
      reset: () => onChange({ top: DEFAULT_TOP }),
    },
  ];

  const info: [string, string][] = [];
  if (prefs.target_skills.length) info.push(['Cel', prefs.target_skills.join(', ')]);
  info.push(['Poziom', prefs.experience_levels === 'auto' ? 'auto' : prefs.experience_levels.join(', ')]);
  info.push([
    'Tryb',
    prefs.workplace.map((w) => ({ remote: 'zdalnie', hybrid: 'hybrydowo', office: 'biuro' })[w]).join(', '),
  ]);
  if (prefs.exclude_keywords.length) info.push(['Wykluczone', prefs.exclude_keywords.join(', ')]);

  return (
    <div className={s.chipsRow} aria-label="Filtry">
      {editable.map((chip) => (
        <ChipEditor key={chip.key} chip={chip} />
      ))}
      {info.map(([label, value]) => (
        <span key={label} className={`${s.filterChip} ${s.filterChipStatic}`} title="Ustawienie z config.toml">
          <span className="muted">{label}</span>
          <span style={{ fontWeight: 500 }}>{value}</span>
        </span>
      ))}
      <button
        type="button"
        aria-pressed={filters.status === 'saved'}
        className={`${s.filterChip} ${filters.status === 'saved' ? s.filterChipOn : ''}`}
        onClick={() => onChange({ status: filters.status === 'saved' ? null : 'saved' })}
      >
        Tylko zapisane
      </button>
    </div>
  );
}

function ChipEditor({ chip }: { chip: EditableChip }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(chip.input);
  const wrapRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useEscape(open, close);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    return () => document.removeEventListener('pointerdown', onPointer);
  }, [open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    chip.apply(draft);
    setOpen(false);
  };

  return (
    <div className={s.chipWrap} ref={wrapRef}>
      <button
        type="button"
        className={`${s.filterChip} ${chip.modified ? s.filterChipOn : ''}`}
        aria-expanded={open}
        onClick={() => {
          setDraft(chip.input);
          setOpen((o) => !o);
        }}
      >
        <span className="muted">{chip.label}</span>
        <span style={{ fontWeight: 500 }}>{chip.value}</span>
        <ChevronDownIcon size={12} />
      </button>
      {open ? (
        <>
          <button type="button" className={s.editorBackdrop} aria-label="Zamknij" onClick={close} />
          <form className={s.editor} onSubmit={submit}>
            <label className={s.editorLabel}>
              {chip.inputLabel}
              <input
                className="input"
                value={draft}
                inputMode={chip.inputMode}
                placeholder={chip.placeholder}
                onChange={(e) => setDraft(e.target.value)}
                autoFocus
              />
            </label>
            <div className={s.editorActions}>
              {chip.modified ? (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    chip.reset();
                    setOpen(false);
                  }}
                >
                  Przywróć z profilu
                </button>
              ) : null}
              <button type="submit" className="btn btn-primary">
                Zastosuj
              </button>
            </div>
          </form>
        </>
      ) : null}
    </div>
  );
}
