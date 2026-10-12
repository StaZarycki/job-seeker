import { useState, type KeyboardEvent, type ReactNode } from 'react';

import { ApiError } from '../api/client';
import { CrossIcon } from './icons';
import { Banner } from './ui';
import s from './forms.module.css';

/** One labelled setting: label + hint on the left (stacked on phones), control on the right. */
export function Field({
  label,
  hint,
  htmlFor,
  error,
  aside,
  children,
}: {
  label: string;
  hint?: ReactNode;
  htmlFor?: string;
  error?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const LabelTag = htmlFor ? 'label' : 'span';
  return (
    <div className={`${s.field} ${aside ? s.fieldWithAside : ''}`}>
      <div className={s.fieldText}>
        <LabelTag className={s.fieldLabel} {...(htmlFor ? { htmlFor } : {})}>
          {label}
        </LabelTag>
        {hint ? <span className={s.fieldHint}>{hint}</span> : null}
      </div>
      <div className={s.fieldControl}>
        {children}
        {error ? (
          <span className={s.fieldError} role="alert">
            {error}
          </span>
        ) : null}
      </div>
      {aside ? <div className={s.fieldAside}>{aside}</div> : null}
    </div>
  );
}

export function TagInput({
  label,
  values,
  onChange,
  disabled = false,
  mono = false,
  placeholder = 'Dodaj i Enter',
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  disabled?: boolean;
  mono?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const add = () => {
    const items = text
      .split(',')
      .map((v) => v.trim())
      .filter((v) => v && !values.includes(v));
    if (items.length) onChange([...values, ...items]);
    setText('');
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      add();
    } else if (event.key === 'Backspace' && !text && values.length) {
      onChange(values.slice(0, -1));
    }
  };
  return (
    <div className={`${s.tags} ${disabled ? s.disabled : ''}`}>
      {values.map((value) => (
        <span key={value} className={`${s.tag} ${mono ? 'mono' : ''}`}>
          {value}
          <button
            type="button"
            className={s.tagRemove}
            aria-label={`Usuń ${value}`}
            disabled={disabled}
            onClick={() => onChange(values.filter((v) => v !== value))}
          >
            <CrossIcon size={11} strokeWidth={2.5} />
          </button>
        </span>
      ))}
      {values.length === 0 && disabled ? <span className="muted">brak</span> : null}
      <input
        className={s.tagInput}
        aria-label={`Dodaj: ${label}`}
        placeholder={placeholder}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
      />
    </div>
  );
}

export interface ChipOption<T extends string> {
  value: T;
  label: string;
  count?: string;
}

export function ToggleChips<T extends string>({
  label,
  options,
  values,
  onChange,
  disabled = false,
  mono = false,
}: {
  label: string;
  options: ChipOption<T>[];
  values: T[];
  onChange: (values: T[]) => void;
  disabled?: boolean;
  mono?: boolean;
}) {
  return (
    <div className={`${s.chips} ${disabled ? s.disabled : ''}`} role="group" aria-label={label}>
      {options.map((option) => {
        const on = values.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={on}
            disabled={disabled}
            className={`${s.chip} ${on ? s.chipOn : ''} ${mono ? 'mono' : ''}`}
            onClick={() => onChange(on ? values.filter((v) => v !== option.value) : [...values, option.value])}
          >
            {option.label}
            {option.count ? <span className={s.chipCount}>{option.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export function Switch({
  label,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={`${s.switch} ${checked ? s.switchOn : ''} ${disabled ? s.disabled : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span className={s.knob} />
    </button>
  );
}

function parseNumber(text: string): number | null {
  const normalized = text.replace(/\s/g, '').replace(',', '.');
  if (normalized === '') return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : Number.NaN;
}

/**
 * Numeric text field. While focused it shows exactly what is typed ("0.", or empty before typing a new
 * number) and reports every valid number; empty means null unless ``required``. On blur it shows the value.
 */
export function NumberInput({
  id,
  label,
  value,
  onChange,
  unit,
  placeholder,
  disabled = false,
  invalid = false,
  required = false,
  width = 110,
}: {
  id?: string;
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  unit?: string;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  required?: boolean;
  width?: number;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const formatted = value === null ? '' : String(value);
  return (
    <span className={s.number}>
      <input
        id={id}
        className={`input mono ${invalid ? s.invalid : ''}`}
        style={{ width }}
        inputMode="decimal"
        aria-label={id ? undefined : label}
        aria-invalid={invalid || undefined}
        value={editing ?? formatted}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => setEditing(formatted)}
        onBlur={() => setEditing(null)}
        onChange={(e) => {
          setEditing(e.target.value);
          const next = parseNumber(e.target.value);
          if (!Number.isNaN(next) && (next !== null || !required)) onChange(next);
        }}
      />
      {unit ? <span className="muted">{unit}</span> : null}
    </span>
  );
}

/** Sticky footer for forms that write config.toml: unsaved count, preview of the changes, and save errors. */
export function SaveBar({
  changes,
  preview,
  saving,
  saved,
  error,
  saveLabel = 'Zapisz w config.toml',
  canSave = true,
  collapseWhenClean = false,
  onSave,
  onDiscard,
  onReload,
}: {
  changes: number;
  preview: string;
  saving: boolean;
  saved: boolean;
  error: Error | null;
  saveLabel?: string;
  canSave?: boolean;
  /** Phones: no bar while there is nothing to save (just "Zapisano" after a save). */
  collapseWhenClean?: boolean;
  onSave: (force: boolean) => void;
  onDiscard: () => void;
  onReload: () => void;
}) {
  const [showPreview, setShowPreview] = useState(false);
  const [copied, setCopied] = useState(false);
  const apiError = error instanceof ApiError ? error : null;
  const dirty = changes > 0;
  const fieldCount = apiError ? Object.keys(apiError.fields).length : 0;
  const status = saving
    ? 'Zapisywanie…'
    : dirty
      ? `Niezapisane zmiany: ${changes}`
      : saved
        ? 'Zapisano w config.toml · przed chwilą'
        : 'Brak zmian';

  const idle = collapseWhenClean && !dirty && !error && !saving;
  return (
    <div className={`${s.saveBar} ${idle ? (saved ? s.saveBarSaved : s.saveBarHidden) : ''}`}>
      {apiError?.code === 'config_conflict' ? (
        <Banner
          tone="warn"
          action={
            <span className={s.saveBarActions}>
              <button type="button" className="btn" onClick={onReload}>
                Wczytaj plik i zachowaj moje zmiany
              </button>
              <button type="button" className={`btn btn-ghost ${s.danger}`} onClick={() => onSave(true)}>
                Nadpisz plik
              </button>
            </span>
          }
        >
          <strong>config.toml zmienił się w międzyczasie.</strong> Plik został edytowany poza aplikacją od czasu
          otwarcia tej strony. Twoje zmiany nie zostały jeszcze zapisane.
        </Banner>
      ) : apiError?.code === 'config_write_failed' ? (
        <Banner
          tone="warn"
          action={
            <span className={s.saveBarActions}>
              <button type="button" className="btn" onClick={() => onSave(false)}>
                Spróbuj ponownie
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  void navigator.clipboard?.writeText(preview).then(() => setCopied(true));
                }}
              >
                {copied ? 'Skopiowano' : 'Kopiuj zmiany'}
              </button>
            </span>
          }
        >
          <strong>Nie można zapisać config.toml.</strong> {apiError.message} Zmiany zostały w formularzu.
        </Banner>
      ) : apiError?.code === 'invalid_request' && fieldCount ? (
        <Banner tone="warn">
          <strong>
            Popraw {fieldCount} {fieldCount === 1 ? 'pole' : fieldCount < 5 ? 'pola' : 'pól'}, żeby zapisać.
          </strong>{' '}
          Błędy są zaznaczone przy polach.
        </Banner>
      ) : error ? (
        <Banner tone="warn">{error.message}</Banner>
      ) : null}
      {showPreview && dirty ? (
        <pre className={s.preview} aria-label="Zmiany w config.toml">
          {preview}
        </pre>
      ) : null}
      <div className={s.saveBarRow}>
        <span role="status" className={dirty ? '' : 'muted'}>
          {status}
        </span>
        <button
          type="button"
          className={`btn btn-ghost ${s.previewToggle}`}
          disabled={!dirty}
          onClick={() => setShowPreview((v) => !v)}
        >
          {showPreview ? 'Ukryj zmiany' : 'Pokaż zmiany'}
        </button>
        <button type="button" className="btn" disabled={!dirty || saving} onClick={onDiscard}>
          Odrzuć zmiany
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!dirty || !canSave || saving}
          onClick={() => onSave(false)}
        >
          {saveLabel}
        </button>
      </div>
    </div>
  );
}
