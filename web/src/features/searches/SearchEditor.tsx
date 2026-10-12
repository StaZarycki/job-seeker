import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';

import { ApiError, type SearchPreferences, type SearchSummary } from '../../api/client';
import {
  useCategories,
  useDeletePreset,
  useSaveDefaultSearch,
  useSavePreset,
  useSources,
  useStartSync,
  useSyncStatus,
} from '../../api/hooks';
import { Field, NumberInput, SaveBar, Switch, TagInput, ToggleChips } from '../../components/forms';
import { diffValues, formatChanges, type Change } from '../../lib/diff';
import { formatNumber } from '../../lib/format';
import {
  LEVELS,
  presetNameError,
  SEARCH_FIELDS,
  SEARCH_GROUPS,
  SOURCE_LABELS,
  WORKPLACE_LABELS,
  type SearchField,
  type SearchKey,
} from '../../lib/searchFields';
import s from './searches.module.css';

interface Draft {
  name: string;
  values: SearchPreferences;
  overridden: SearchKey[];
}

function pick(values: SearchPreferences, keys: SearchKey[]): Partial<SearchPreferences> {
  return Object.fromEntries(keys.map((key) => [key, values[key]]));
}

/**
 * Editor of the default search (``summary.name === null``) or of a preset. A preset only stores the fields it
 * overrides; the others show the default's value, greyed out, until "Nadpisz".
 */
export function SearchEditor({
  summary,
  base,
  version,
  takenNames,
  stats,
  header,
  onSaved,
  onDeleted,
  onReload,
}: {
  summary: SearchSummary | null; // null: a new preset
  base: SearchPreferences;
  version: string;
  takenNames: string[];
  stats?: string;
  header?: ReactNode;
  onSaved: (name: string | null) => void;
  onDeleted: () => void;
  onReload: () => void;
}) {
  const isNew = summary === null;
  const isDefault = summary?.name === null;
  const originalName = summary?.name ?? '';
  const initial: Draft = summary
    ? { name: originalName, values: summary.preferences, overridden: summary.overridden as SearchKey[] }
    : { name: '', values: base, overridden: [] };
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const current = draft ?? initial;

  const saveDefault = useSaveDefaultSearch();
  const savePreset = useSavePreset();
  const deletePreset = useDeletePreset();
  const mutation = isDefault ? saveDefault : savePreset;
  const syncStatus = useSyncStatus();
  const startSync = useStartSync();
  const sources = useSources();
  const categories = useCategories('justjoin');

  const nameError = isDefault
    ? null
    : presetNameError(
        current.name,
        takenNames.filter((n) => n !== originalName),
      );
  const showNameError = Boolean(nameError) && (current.name !== '' || draft !== null);
  const prefix = isDefault ? 'search' : `searches.${current.name || '<nazwa>'}`;
  const changes: Change[] = isDefault
    ? diffValues(initial.values, current.values, prefix)
    : [
        ...(current.name !== initial.name
          ? [{ section: 'searches', key: 'nazwa', from: initial.name, to: current.name }]
          : []),
        // Overriding a field adds a key to the preset even when its value equals the default's.
        ...diffValues(pick(initial.values, initial.overridden), pick(current.values, current.overridden), prefix),
      ];
  const fields = mutation.error instanceof ApiError ? mutation.error.fields : {};
  const fieldError = (key: string) => Object.entries(fields).find(([path]) => path.split('.').includes(key))?.[1];

  const update = (patch: Partial<Draft>) => setDraft({ ...current, ...patch });
  const setValue = <K extends SearchKey>(key: K, value: SearchPreferences[K]) =>
    update({ values: { ...current.values, [key]: value } });
  const override = (key: SearchKey) =>
    update({ overridden: [...current.overridden, key], values: { ...current.values, [key]: base[key] } });
  const inherit = (key: SearchKey) =>
    update({
      overridden: current.overridden.filter((k) => k !== key),
      values: { ...current.values, [key]: base[key] },
    });

  const onSave = (force: boolean) => {
    const done = () => {
      setDraft(null);
      onSaved(isDefault ? null : current.name);
    };
    if (isDefault) {
      saveDefault.mutate({ version, force, preferences: current.values }, { onSuccess: done });
      return;
    }
    savePreset.mutate(
      {
        name: isNew ? current.name : originalName,
        version,
        force,
        overrides: pick(current.values, current.overridden),
        create: isNew,
        renameTo: !isNew && current.name !== originalName ? current.name : null,
      },
      { onSuccess: done },
    );
  };

  const syncing = syncStatus.data?.running ?? false;
  const categoryOptions = [
    ...(categories.data ?? []).map((c) => ({
      value: c.key,
      label: c.key,
      count: c.count === null ? undefined : formatNumber(c.count),
    })),
    ...current.values.categories
      .filter((c) => !categories.data?.some((x) => x.key === c))
      .map((c) => ({ value: c, label: c })),
  ];
  const sourceOptions = (sources.data ?? [{ name: 'justjoin' }]).map((src) => ({
    value: src.name,
    label: SOURCE_LABELS[src.name] ?? src.name,
  }));

  const renderControl = (field: SearchField, locked: boolean) => {
    const value = current.values[field.key];
    const invalid = Boolean(fieldError(field.key));
    switch (field.type) {
      case 'sources':
      case 'categories':
        return (
          <ToggleChips
            label={field.label}
            options={field.type === 'sources' ? sourceOptions : categoryOptions}
            values={value as string[]}
            disabled={locked}
            onChange={(v) => setValue(field.key, v as never)}
          />
        );
      case 'workplace':
        return (
          <ToggleChips
            label={field.label}
            options={Object.entries(WORKPLACE_LABELS).map(([v, label]) => ({ value: v, label }))}
            values={value as string[]}
            disabled={locked}
            onChange={(v) => setValue('workplace', v as SearchPreferences['workplace'])}
          />
        );
      case 'level': {
        const auto = value === 'auto';
        return (
          <div className={s.level}>
            <div className={s.levelModes} role="group" aria-label="Sposób wyboru poziomu">
              {(
                [
                  ['auto', 'Automatycznie'],
                  ['list', 'Wybrane poziomy'],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={(mode === 'auto') === auto}
                  disabled={locked}
                  className={`${s.levelMode} ${(mode === 'auto') === auto ? s.levelModeOn : ''}`}
                  onClick={() => setValue('experience_levels', mode === 'auto' ? 'auto' : ['mid', 'senior'])}
                >
                  {label}
                </button>
              ))}
            </div>
            {auto ? null : (
              <ToggleChips
                label="Poziomy"
                mono
                options={LEVELS.map((l) => ({ value: l, label: l }))}
                values={value as string[]}
                disabled={locked}
                onChange={(v) => setValue('experience_levels', v as SearchPreferences['experience_levels'])}
              />
            )}
          </div>
        );
      }
      case 'tags':
        return (
          <TagInput
            label={field.label}
            values={value as string[]}
            disabled={locked}
            onChange={(v) => setValue(field.key, v as never)}
          />
        );
      case 'switch':
        return (
          <Switch
            label={field.label}
            checked={Boolean(value)}
            disabled={locked}
            onChange={(v) => setValue('onsite_only_in_preferred_cities', v)}
          />
        );
      case 'number':
        return (
          <NumberInput
            label={field.label}
            value={(value as number | null) ?? null}
            unit={field.unit}
            placeholder={field.placeholder}
            disabled={locked}
            invalid={invalid}
            width={120}
            onChange={(v) => setValue(field.key, v as never)}
          />
        );
    }
  };

  return (
    <section
      className={s.editor}
      aria-label={isDefault ? 'Edycja: Domyślne' : `Edycja profilu ${current.name || 'nowego'}`}
    >
      {header}
      <div className={s.editorHead}>
        <div className={s.editorTitle}>
          {isDefault ? (
            <>
              <h2 className={s.editorName}>Domyślne</h2>
              <span className="muted" style={{ fontSize: 12.5 }}>
                Sekcja <span className="mono">[search]</span> · baza dla wszystkich profili
              </span>
            </>
          ) : (
            <>
              <label className={s.nameLabel}>
                Nazwa profilu
                <input
                  className={`input mono ${s.nameInput} ${showNameError ? s.invalid : ''}`}
                  value={current.name}
                  placeholder="np. go"
                  aria-invalid={showNameError || undefined}
                  onChange={(e) => update({ name: e.target.value.trim() })}
                />
              </label>
              <span className={showNameError ? s.error : 'muted'} style={{ fontSize: 12 }}>
                {showNameError
                  ? nameError
                  : (fieldError('name') ??
                    `W config.toml: [searches.${current.name || '<nazwa>'}] · nazwa pojawia się w wyborze wyszukiwania i w URL`)}
              </span>
            </>
          )}
        </div>
        {isNew ? null : (
          <div className={s.editorActions}>
            {stats ? <span className="mono muted">{stats}</span> : null}
            <button
              type="button"
              className="btn"
              disabled={syncing || startSync.isPending}
              onClick={() => startSync.mutate({ search: summary?.name ?? null })}
            >
              {syncing ? 'Synchronizuję…' : 'Synchronizuj'}
            </button>
            <Link to={summary?.name ? `/?search=${encodeURIComponent(summary.name)}` : '/'} className="btn btn-primary">
              Pokaż oferty
            </Link>
            {isDefault ? null : (
              <button type="button" className={`btn btn-ghost ${s.deleteBtn}`} onClick={() => setConfirmDelete(true)}>
                Usuń
              </button>
            )}
          </div>
        )}
      </div>

      {confirmDelete ? (
        <div role="alert" className={s.confirm}>
          <span>
            Usunąć profil <span className="mono">{originalName}</span>? Sekcja{' '}
            <span className="mono">[searches.{originalName}]</span> zniknie z config.toml. Pobrane oferty zostają.
          </span>
          <button type="button" className="btn" onClick={() => setConfirmDelete(false)}>
            Anuluj
          </button>
          <button
            type="button"
            className={`btn ${s.confirmDelete}`}
            disabled={deletePreset.isPending}
            onClick={() => deletePreset.mutate({ name: originalName, version }, { onSuccess: onDeleted })}
          >
            Usuń profil
          </button>
          {deletePreset.error ? <span className={s.error}>{deletePreset.error.message}</span> : null}
        </div>
      ) : null}

      {isNew ? (
        <p className={`note ${s.newNote}`}>
          Nowy profil dziedziczy wszystkie pola z Domyślnych. Kliknij „Nadpisz” przy tym, co ma być inne – np. kategorie
          i technologie docelowe.
        </p>
      ) : null}

      <div className={s.groups}>
        {SEARCH_GROUPS.map((title, group) => (
          <fieldset key={title} className={s.group}>
            <legend className={s.groupTitle}>{title}</legend>
            {SEARCH_FIELDS.filter((f) => f.group === group).map((field) => {
              const own = isDefault || current.overridden.includes(field.key);
              return (
                <Field
                  key={field.key}
                  label={field.label}
                  hint={field.hint}
                  error={fieldError(field.key)}
                  aside={
                    isDefault ? undefined : own ? (
                      <>
                        <span className={s.overriddenPill}>nadpisane</span>
                        <button
                          type="button"
                          className={s.inheritBtn}
                          aria-label={`Dziedzicz ${field.label} z Domyślnych`}
                          onClick={() => inherit(field.key)}
                        >
                          Dziedzicz
                        </button>
                      </>
                    ) : (
                      <>
                        <span className={`muted ${s.inheritedNote}`}>z Domyślnych</span>
                        <button
                          type="button"
                          className={`btn ${s.overrideBtn}`}
                          aria-label={`Nadpisz ${field.label}`}
                          onClick={() => override(field.key)}
                        >
                          Nadpisz
                        </button>
                      </>
                    )
                  }
                >
                  {renderControl(field, !own)}
                </Field>
              );
            })}
          </fieldset>
        ))}
      </div>

      {!isDefault && !isNew && !confirmDelete ? (
        <button type="button" className={`btn ${s.phoneDelete}`} onClick={() => setConfirmDelete(true)}>
          Usuń profil
        </button>
      ) : null}

      <SaveBar
        changes={changes.length}
        preview={formatChanges(changes)}
        saving={mutation.isPending}
        saved={mutation.isSuccess && draft === null}
        error={mutation.error}
        canSave={!nameError}
        saveLabel={isNew ? 'Utwórz profil' : 'Zapisz w config.toml'}
        onSave={onSave}
        onDiscard={() => {
          setDraft(null);
          mutation.reset();
        }}
        onReload={() => {
          mutation.reset();
          onReload();
        }}
      />
    </section>
  );
}
