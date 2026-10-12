import { useState } from 'react';

import { ApiError, type EnvKeyStatus } from '../../api/client';
import { useEnvKeys, useRemoveEnvKey, useSetEnvKey } from '../../api/hooks';
import { Skeleton } from '../../components/ui';
import s from './settings.module.css';

const NOTES: Record<string, string> = {
  ANTHROPIC_WORKSPACE_ID: 'Tylko dla kluczy organizacji bez przypisanego workspace',
  OPENAI_API_KEY: 'Lokalna Ollama nie wymaga klucza',
};

/** API keys in backend/.env: write-only; the page only learns whether a key is set and its last characters. */
export function ApiKeys() {
  const keys = useEnvKeys();
  return (
    <div className={s.keys}>
      <p className="muted" style={{ fontSize: 12.5 }}>
        Klucz zapisuje się w pliku .env na serwerze. Strona nigdy go nie wyświetla ani nie pobiera z powrotem – widać
        tylko, czy jest ustawiony.
      </p>
      {keys.error ? <p className={s.error}>{(keys.error as Error).message}</p> : null}
      {keys.data ? (
        keys.data.map((key) => <KeyRow key={key.name} item={key} />)
      ) : keys.isPending ? (
        <Skeleton width="60%" />
      ) : null}
    </div>
  );
}

function KeyRow({ item }: { item: EnvKeyStatus }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const save = useSetEnvKey();
  const remove = useRemoveEnvKey();
  const secret = item.name !== 'ANTHROPIC_WORKSPACE_ID';
  const error = save.error ?? remove.error;
  const close = () => {
    setEditing(false);
    setValue('');
    save.reset();
    remove.reset();
  };

  return (
    <div className={s.keyRow}>
      <div className={s.keyName}>
        <span style={{ fontWeight: 500, fontSize: 13.5 }}>{item.label}</span>
        <span className="mono muted" style={{ fontSize: 11.5 }}>
          {item.name}
        </span>
      </div>
      <div className={s.keyBody}>
        <div className={s.keyStatus}>
          <span className={`${s.pill} ${item.set ? s.pillOn : ''}`}>
            <span className={s.dot} />
            {item.set ? 'ustawiony' : 'brak'}
          </span>
          <span className="muted" style={{ fontSize: 12 }}>
            {item.set ? item.hint : NOTES[item.name]}
          </span>
          {editing ? null : (
            <button type="button" className={`btn ${s.keyAction}`} onClick={() => setEditing(true)}>
              {item.set ? 'Zmień' : 'Dodaj'}
            </button>
          )}
        </div>
        {editing ? (
          <form
            className={s.keyForm}
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate({ name: item.name, value }, { onSuccess: close });
            }}
          >
            <input
              className="input mono"
              type={secret ? 'password' : 'text'}
              autoComplete="off"
              aria-label={`${item.label}: nowa wartość`}
              placeholder={item.name === 'ANTHROPIC_API_KEY' ? 'sk-ant-…' : secret ? 'sk-…' : 'wrkspc_…'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
            />
            <button type="submit" className="btn btn-primary" disabled={!value.trim() || save.isPending}>
              Zapisz
            </button>
            <button type="button" className="btn" onClick={close}>
              Anuluj
            </button>
            {item.set ? (
              <button
                type="button"
                className={`btn btn-ghost ${s.danger}`}
                disabled={remove.isPending}
                onClick={() => remove.mutate(item.name, { onSuccess: close })}
              >
                Usuń z .env
              </button>
            ) : null}
          </form>
        ) : null}
        {error ? (
          <span className={s.error} role="alert">
            {error instanceof ApiError ? (Object.values(error.fields)[0] ?? error.message) : error.message}
          </span>
        ) : null}
      </div>
    </div>
  );
}
