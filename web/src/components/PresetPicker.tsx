import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router';

import type { SearchSummary } from '../api/client';
import { useEscape } from '../lib/hooks';
import { countLabel, OFFER_FORMS } from '../lib/format';
import { presetDescription, presetLabel } from '../lib/presets';
import { CheckIcon, ChevronDownIcon } from './icons';
import s from './PresetPicker.module.css';

/**
 * Search preset selector: a dropdown on desktop, a bottom sheet on phones (same markup, CSS decides).
 */
export function PresetPicker({
  value,
  searches,
  onChange,
}: {
  value: string | null;
  searches: SearchSummary[];
  onChange: (name: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
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

  return (
    <div className={s.wrap} ref={wrapRef}>
      <button
        type="button"
        className={s.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={s.triggerLabel}>Wyszukiwanie</span>
        <span className={s.triggerValue}>{presetLabel(value)}</span>
        <ChevronDownIcon size={12} className={s.chevron} />
      </button>
      {open ? (
        <>
          <button type="button" className={s.backdrop} aria-label="Zamknij listę" onClick={close} />
          <div className={s.menu} id={menuId} role="listbox" aria-label="Profile wyszukiwania">
            <div className={s.sheetHandle} />
            <div className={s.sheetTitle}>Wyszukiwanie</div>
            {searches.map((summary) => {
              const active = summary.name === value;
              const disabled = summary.needs_sync;
              return (
                <button
                  key={summary.name ?? '__default'}
                  type="button"
                  role="option"
                  aria-selected={active}
                  disabled={disabled}
                  className={`${s.option} ${active ? s.optionActive : ''}`}
                  onClick={() => {
                    onChange(summary.name);
                    setOpen(false);
                  }}
                >
                  <span className={s.optionBody}>
                    <span className={s.optionName}>{presetLabel(summary.name)}</span>
                    <span className={s.optionDesc}>{presetDescription(summary)}</span>
                  </span>
                  <span className={s.optionCount}>{disabled ? '—' : countLabel(summary.passed, OFFER_FORMS)}</span>
                  {active ? <CheckIcon size={14} className={s.check} /> : null}
                </button>
              );
            })}
            <div className={s.divider} />
            <Link to="/searches" className={`${s.menuLink} ${s.menuLinkPrimary}`} onClick={close}>
              + Nowy profil wyszukiwania
            </Link>
            <Link to="/searches" className={`${s.menuLink} ${s.menuLinkMuted}`} onClick={close}>
              Zarządzaj profilami
            </Link>
          </div>
        </>
      ) : null}
    </div>
  );
}
