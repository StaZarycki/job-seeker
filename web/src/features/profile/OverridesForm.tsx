import { useId, useMemo, useState, type FormEvent } from 'react';

import type { CandidateProfile, ProfileOverrides } from '../../api/client';
import { useOverrides, useSaveOverrides } from '../../api/hooks';
import { ChevronDownIcon, ChevronUpIcon, CrossIcon } from '../../components/icons';
import s from './profile.module.css';

interface YearRow {
  id: number;
  name: string;
  years: string;
}

interface Draft {
  years: string;
  seniority: string;
  rows: YearRow[];
  add: string;
  remove: string;
  notes: string;
}

let rowId = 0;

function toDraft(o: ProfileOverrides): Draft {
  return {
    years: o.years_of_experience != null ? String(o.years_of_experience) : '',
    seniority: o.seniority ?? '',
    rows: Object.entries(o.skill_years).map(([name, value]) => ({ id: ++rowId, name, years: String(value) })),
    add: o.add_skills.join(', '),
    remove: o.remove_skills.join(', '),
    notes: o.extra_notes ?? '',
  };
}

const list = (value: string) =>
  value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);

/** Manual corrections (profile.overrides.toml) - they survive CV changes. */
export function OverridesForm({ profile }: { profile: CandidateProfile }) {
  const overrides = useOverrides();
  const save = useSaveOverrides();
  const [open, setOpen] = useState(false);
  const [edited, setEdited] = useState<Draft | null>(null);
  const bodyId = useId();
  const loaded = useMemo(() => (overrides.data ? toDraft(overrides.data) : null), [overrides.data]);
  // Until the user edits something, the form shows what is saved in profile.overrides.toml.
  const draft = edited ?? loaded;

  const changes = overrides.data
    ? Object.keys(overrides.data.skill_years).length +
      overrides.data.add_skills.length +
      overrides.data.remove_skills.length +
      (overrides.data.years_of_experience != null ? 1 : 0) +
      (overrides.data.seniority ? 1 : 0) +
      (overrides.data.extra_notes ? 1 : 0)
    : 0;

  const update = (patch: Partial<Draft>) => setEdited(draft ? { ...draft, ...patch } : null);
  const updateRow = (id: number, patch: Partial<YearRow>) =>
    update({ rows: (draft?.rows ?? []).map((r) => (r.id === id ? { ...r, ...patch } : r)) });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!draft || !overrides.data) return;
    const skillYears: Record<string, number> = {};
    for (const row of draft.rows) {
      const value = Number(row.years.replace(',', '.'));
      if (row.name.trim() && Number.isFinite(value)) skillYears[row.name.trim()] = value;
    }
    const yearsValue = Number(draft.years.replace(',', '.'));
    save.mutate(
      {
        ...overrides.data,
        years_of_experience: draft.years.trim() && Number.isFinite(yearsValue) ? yearsValue : null,
        seniority: (draft.seniority || null) as ProfileOverrides['seniority'],
        skill_years: skillYears,
        add_skills: list(draft.add),
        remove_skills: list(draft.remove),
        extra_notes: draft.notes.trim() || null,
      },
      { onSuccess: () => setEdited(null) },
    );
  };

  return (
    <section className={`card ${s.overrides}`} aria-label="Ręczne poprawki">
      <button
        type="button"
        className={s.overridesToggle}
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((o) => !o)}
      >
        <span style={{ flex: '1 1 auto', minWidth: 0, textAlign: 'left' }}>
          <span className="card-title" style={{ display: 'block' }}>
            Ręczne poprawki
          </span>
          <span className="section-hint">
            profile.overrides.toml · przetrwają zmianę CV{changes ? ` · ${changes} zmian` : ''}
          </span>
        </span>
        <span className={s.toggleIcon}>{open ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}</span>
      </button>

      <form id={bodyId} className={`${s.overridesBody} ${open ? s.overridesOpen : ''}`} onSubmit={submit}>
        {draft ? (
          <>
            <div className={s.formGrid}>
              <label className={s.field}>
                Staż (lata)
                <input
                  className="input"
                  type="number"
                  step="0.5"
                  min="0"
                  placeholder={`z CV: ${profile.years_of_experience}`}
                  value={draft.years}
                  onChange={(e) => update({ years: e.target.value })}
                />
              </label>
              <label className={s.field}>
                Poziom
                <select
                  className="input"
                  value={draft.seniority}
                  onChange={(e) => update({ seniority: e.target.value })}
                >
                  <option value="">z CV ({profile.seniority})</option>
                  <option value="junior">junior</option>
                  <option value="mid">mid</option>
                  <option value="senior">senior</option>
                </select>
              </label>
            </div>

            <fieldset className={s.fieldset}>
              <legend className={s.legend}>Lata per technologia</legend>
              {draft.rows.map((row) => (
                <div className={s.yearRow} key={row.id}>
                  <input
                    className="input"
                    aria-label="Technologia"
                    value={row.name}
                    onChange={(e) => updateRow(row.id, { name: e.target.value })}
                  />
                  <input
                    className={`input mono ${s.yearsInput}`}
                    aria-label={`Lata: ${row.name}`}
                    type="number"
                    step="0.5"
                    min="0"
                    value={row.years}
                    onChange={(e) => updateRow(row.id, { years: e.target.value })}
                  />
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Usuń wiersz ${row.name}`}
                    onClick={() => update({ rows: draft.rows.filter((r) => r.id !== row.id) })}
                  >
                    <CrossIcon size={13} strokeWidth={2} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-dashed"
                style={{ alignSelf: 'flex-start' }}
                onClick={() => update({ rows: [...draft.rows, { id: ++rowId, name: '', years: '' }] })}
              >
                + Dodaj technologię
              </button>
            </fieldset>

            <div className={s.formGrid}>
              <label className={s.field}>
                Dodaj umiejętności
                <input
                  className="input"
                  placeholder="np. Kafka, Kubernetes"
                  value={draft.add}
                  onChange={(e) => update({ add: e.target.value })}
                />
              </label>
              <label className={s.field}>
                Usuń umiejętności
                <input
                  className="input"
                  placeholder="np. Scrum"
                  value={draft.remove}
                  onChange={(e) => update({ remove: e.target.value })}
                />
              </label>
            </div>

            <label className={s.field}>
              Notatki dla oceny AI
              <textarea
                className="input"
                rows={3}
                placeholder="np. Szukam roli backendowej, bez frontendu."
                value={draft.notes}
                onChange={(e) => update({ notes: e.target.value })}
              />
            </label>

            <div className={s.formFooter}>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>
                {save.isPending ? 'Zapisuję…' : 'Zapisz poprawki'}
              </button>
              <span className="section-hint" role="status">
                {save.isSuccess ? 'Zapisano – profil zaktualizowany.' : 'Zmiana poprawek unieważnia zapisane oceny AI.'}
              </span>
            </div>
            {save.error ? <p className={s.error}>{(save.error as Error).message}</p> : null}
          </>
        ) : (
          <p className="muted">Wczytywanie poprawek…</p>
        )}
      </form>
    </section>
  );
}
