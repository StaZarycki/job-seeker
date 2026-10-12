import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';

import { ApiError, type ConfigResponse } from '../../api/client';
import { useConfig, useSaveConfig, type ConfigSections } from '../../api/hooks';
import { ApiErrorState } from '../../components/ApiErrorState';
import { Field, NumberInput, SaveBar, TagInput } from '../../components/forms';
import { ChevronDownIcon, ChevronUpIcon } from '../../components/icons';
import { Banner, Segmented, Skeleton } from '../../components/ui';
import { diffValues, formatChanges, sameValue } from '../../lib/diff';
import { percent } from '../../lib/format';
import { PHONE_QUERY, useMediaQuery } from '../../lib/hooks';
import { DEFAULT_WEIGHTS, WEIGHT_LABELS } from '../../lib/weights';
import { ApiKeys } from './ApiKeys';
import s from './settings.module.css';

type Sections = Required<ConfigSections>;
type SectionId = 'matching' | 'ai' | 'keys' | 'justjoin' | 'advanced';

const MODELS: [string, string][] = [
  ['claude-haiku-4-5', 'szybki i tani · domyślny'],
  ['claude-sonnet-5-5', 'dokładniejszy'],
  ['claude-opus-5-5', 'najdokładniejszy, najdroższy'],
];

function sectionsOf(config: ConfigResponse): Sections {
  const { matching, ai, justjoin, paths, api } = config;
  return { matching, ai, justjoin, paths, api };
}

function decimal(value: number): string {
  return value.toFixed(1).replace('.', ',');
}

export function SettingsPage() {
  const config = useConfig();
  const save = useSaveConfig();
  const phone = useMediaQuery(PHONE_QUERY);
  const [draft, setDraft] = useState<Sections | null>(null);
  const [open, setOpen] = useState<SectionId | null>('matching');
  const [advancedOpen, setAdvancedOpen] = useState(false);

  if (!config.data) {
    return (
      <div>
        <Header />
        <div className="page">
          {config.error ? (
            <ApiErrorState error={config.error} onRetry={() => void config.refetch()} />
          ) : (
            <div className="card">
              <Skeleton width="30%" height={14} />
              <Skeleton width="70%" />
              <Skeleton width="55%" />
            </div>
          )}
        </div>
      </div>
    );
  }

  const loaded = config.data;
  const base = sectionsOf(loaded);
  const current = draft ?? base;
  const changes = diffValues(base, current);
  const fieldError = (path: string) => (save.error instanceof ApiError ? save.error.fields[path] : undefined);
  const set = <K extends keyof Sections>(section: K, patch: Partial<Sections[K]>) => {
    setDraft({ ...current, [section]: { ...current[section], ...patch } });
  };
  const onSave = (force: boolean) => {
    const sections: ConfigSections = {};
    for (const key of Object.keys(current) as (keyof Sections)[]) {
      if (!sameValue(current[key], base[key])) Object.assign(sections, { [key]: current[key] });
    }
    save.mutate({ version: loaded.version, force, sections }, { onSuccess: () => setDraft(null) });
  };
  const sectionProps = (id: SectionId) => ({
    id,
    phone,
    open: phone ? open === id : true,
    onToggle: () => setOpen(open === id ? null : id),
  });

  const { matching, ai, justjoin, paths, api } = current;
  const weightSum = WEIGHT_LABELS.reduce((sum, [key]) => sum + matching.weights[key], 0) || 1;
  const anthropic = ai.provider === 'anthropic';
  const transferYears = 4 * matching.experience.transfer_ratio;

  return (
    <div className={s.root}>
      <Header file={loaded.config_file} showNav={!phone} />
      <div className={`page ${s.page}`}>
        {loaded.restart_required ? (
          <Banner tone="warn">
            <strong>Zapisano.</strong> Nowe ścieżki i adresy frontendu zaczną działać po restarcie backendu:{' '}
            <span className="mono">docker compose restart backend</span> albo ponowne{' '}
            <span className="mono">jobseeker serve</span>.
          </Banner>
        ) : null}
        <p className="muted" style={{ fontSize: 12.5 }}>
          Filtry i słowa kluczowe wyszukiwań ustawiasz na ekranie <Link to="/searches">Wyszukiwania</Link>.
        </p>

        <Section
          {...sectionProps('matching')}
          title="Dopasowanie"
          toml="[matching]"
          summary={`${matching.mode === 'ai' ? 'AI' : 'Standard'} · wagi · doświadczenie ${percent(matching.experience.transfer_ratio)}`}
        >
          <Field
            label="Domyślny tryb"
            hint="Przy otwarciu listy ofert i w CLI bez --mode"
            error={fieldError('matching.mode')}
          >
            <div className={s.inline}>
              <Segmented
                label="Domyślny tryb"
                value={matching.mode}
                options={[
                  { value: 'basic', label: 'Standard' },
                  { value: 'ai', label: 'AI' },
                ]}
                onChange={(mode) => set('matching', { mode })}
              />
              <span className="muted" style={{ fontSize: 12 }}>
                {matching.mode === 'ai'
                  ? 'Lista od razu wysyła zapytania do modelu – to kosztuje'
                  : 'Darmowy; AI włączasz przełącznikiem na liście ofert'}
              </span>
            </div>
          </Field>
          <Field
            label="Wagi wyniku Standard"
            hint={
              <>
                Liczy się udział każdej wagi w sumie – nie muszą sumować się do 1.
                <button
                  type="button"
                  className={`btn ${s.smallBtn}`}
                  onClick={() => set('matching', { weights: DEFAULT_WEIGHTS })}
                >
                  Przywróć domyślne
                </button>
              </>
            }
          >
            <div className={s.weights}>
              {WEIGHT_LABELS.map(([key, label]) => (
                <div className={s.weightRow} key={key}>
                  <label htmlFor={`weight-${key}`}>{label}</label>
                  <input
                    id={`weight-${key}`}
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={matching.weights[key]}
                    onChange={(e) =>
                      set('matching', { weights: { ...matching.weights, [key]: Number(e.target.value) } })
                    }
                  />
                  <span className="mono">{matching.weights[key].toFixed(2)}</span>
                  <span className="mono muted">{percent(matching.weights[key] / weightSum)}</span>
                </div>
              ))}
              <span className="mono muted" style={{ fontSize: 12 }}>
                suma wag {weightSum.toFixed(2)} · udział = waga / suma
              </span>
            </div>
          </Field>
          <Field label="Przenoszenie doświadczenia" hint="Jak staż liczy się w technologiach spoza Twoich stanowisk">
            <div className={s.ratios}>
              <Ratio
                id="transfer"
                label="Ogólny staż w nieznanej technologii"
                value={matching.experience.transfer_ratio}
                onChange={(v) => set('matching', { experience: { ...matching.experience, transfer_ratio: v } })}
                example={`Przy 4 latach stażu oferta C++ (bez stanowiska z C++) liczy ~${decimal(transferYears)} roku → poziom ${transferYears < 2 ? 'junior' : 'mid'}.`}
              />
              <Ratio
                id="declared"
                label="Umiejętność z CV bez stanowiska"
                value={matching.experience.declared_ratio}
                onChange={(v) => set('matching', { experience: { ...matching.experience, declared_ratio: v } })}
                example={`Technologia wymieniona w CV, ale w żadnej pozycji: liczy się ${percent(matching.experience.declared_ratio)} ogólnego stażu.`}
              />
            </div>
          </Field>
        </Section>

        <Section
          {...sectionProps('ai')}
          title="Model AI"
          toml="[ai]"
          aside="Używany tylko w trybie AI i przy „Oceń przez AI”"
          summary={`${ai.model} · top ${ai.top_n} · ${percent(ai.weight)} AI`}
        >
          <Field label="Dostawca" error={fieldError('ai.provider')}>
            <div className={s.providers} role="group" aria-label="Dostawca">
              {(
                [
                  ['anthropic', 'Anthropic (Claude)', 'Klucz ANTHROPIC_API_KEY'],
                  ['openai_compatible', 'Zgodny z OpenAI', 'OpenAI, OpenRouter, Ollama, LM Studio'],
                ] as const
              ).map(([value, label, desc]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={ai.provider === value}
                  className={`${s.provider} ${ai.provider === value ? s.providerOn : ''}`}
                  onClick={() =>
                    set('ai', {
                      provider: value,
                      model: value === base.ai.provider ? base.ai.model : value === 'anthropic' ? MODELS[0]![0] : '',
                    })
                  }
                >
                  <span style={{ fontWeight: 500 }}>{label}</span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {desc}
                  </span>
                </button>
              ))}
            </div>
          </Field>
          <Field
            label="Model"
            htmlFor="ai-model"
            hint={anthropic ? 'Identyfikator modelu Claude' : 'Nazwa modelu u dostawcy, np. gpt-4o-mini, llama3.1'}
            error={fieldError('ai.model')}
          >
            <input
              id="ai-model"
              className={`input mono ${s.medium}`}
              value={ai.model}
              onChange={(e) => set('ai', { model: e.target.value })}
            />
            {anthropic ? (
              <div className={s.suggestions}>
                {MODELS.map(([id, note]) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={ai.model === id}
                    className={`${s.suggestion} ${ai.model === id ? s.suggestionOn : ''}`}
                    onClick={() => set('ai', { model: id })}
                  >
                    <span className="mono">{id}</span>
                    <span className="muted">{note}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </Field>
          {anthropic ? null : (
            <Field
              label="Adres API"
              htmlFor="ai-url"
              hint="Puste = OpenAI. Ollama, LM Studio, OpenRouter: ich adres"
              error={fieldError('ai.base_url')}
            >
              <input
                id="ai-url"
                className={`input mono ${s.medium}`}
                placeholder="http://localhost:11434/v1"
                value={ai.base_url ?? ''}
                onChange={(e) => set('ai', { base_url: e.target.value.trim() || null })}
              />
            </Field>
          )}
          <Field
            label="Ocenianych ofert"
            htmlFor="ai-top"
            hint="Najlepsze wg wyniku Standard"
            error={fieldError('ai.top_n')}
          >
            <NumberInput
              id="ai-top"
              label="Ocenianych ofert"
              value={ai.top_n}
              unit="ofert z góry rankingu"
              width={80}
              invalid={Boolean(fieldError('ai.top_n'))}
              required
              onChange={(v) => v !== null && set('ai', { top_n: v })}
            />
            <span className="muted" style={{ fontSize: 12 }}>
              Każda nowa ocena to jedno płatne zapytanie. Oceny są zapamiętywane, więc ponowne otwarcie listy nic nie
              kosztuje.
            </span>
          </Field>
          <Field label="Udział oceny AI" htmlFor="ai-weight" hint="W wyniku końcowym ocenionej oferty">
            <div className={s.slider}>
              <input
                id="ai-weight"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={ai.weight}
                onChange={(e) => set('ai', { weight: Number(e.target.value) })}
              />
              <span className="mono">
                wynik = {percent(ai.weight)} AI + {percent(1 - ai.weight)} Standard
              </span>
            </div>
          </Field>
          <Field
            label="Równoległe zapytania"
            htmlFor="ai-conc"
            hint="Więcej = szybciej, ale łatwiej o limit dostawcy"
            error={fieldError('ai.max_concurrency')}
          >
            <NumberInput
              id="ai-conc"
              label="Równoległe zapytania"
              value={ai.max_concurrency}
              width={80}
              invalid={Boolean(fieldError('ai.max_concurrency'))}
              required
              onChange={(v) => v !== null && set('ai', { max_concurrency: v })}
            />
          </Field>
          <Field
            label="Zmienna z kluczem"
            htmlFor="ai-key-env"
            hint="Puste = standardowa dla dostawcy (ANTHROPIC_API_KEY / OPENAI_API_KEY)"
            error={fieldError('ai.api_key_env')}
          >
            <input
              id="ai-key-env"
              className={`input mono ${s.medium}`}
              placeholder={anthropic ? 'ANTHROPIC_API_KEY' : 'OPENAI_API_KEY'}
              value={ai.api_key_env ?? ''}
              onChange={(e) => set('ai', { api_key_env: e.target.value.trim() || null })}
            />
          </Field>
        </Section>

        <Section
          {...sectionProps('keys')}
          title="Klucze API"
          toml="backend/.env"
          summary="Anthropic, workspace, OpenAI"
        >
          <ApiKeys />
        </Section>

        <Section
          {...sectionProps('justjoin')}
          title="JustJoin.it"
          toml="[justjoin]"
          aside="Pobieranie ofert przy synchronizacji"
          summary={`${justjoin.page_size} ofert na stronę · ${decimal(justjoin.request_delay_s)} s · ${justjoin.max_retries} ponowienia`}
        >
          <Field
            label="Ofert na stronę"
            htmlFor="jj-page"
            hint="Ile ofert w jednym zapytaniu (1–100)"
            error={fieldError('justjoin.page_size')}
          >
            <NumberInput
              id="jj-page"
              label="Ofert na stronę"
              value={justjoin.page_size}
              unit="ofert"
              width={80}
              invalid={Boolean(fieldError('justjoin.page_size'))}
              required
              onChange={(v) => v !== null && set('justjoin', { page_size: v })}
            />
          </Field>
          <Field
            label="Odstęp między zapytaniami"
            htmlFor="jj-delay"
            hint="Mniejszy = szybciej, ale łatwiej o blokadę"
            error={fieldError('justjoin.request_delay_s')}
          >
            <NumberInput
              id="jj-delay"
              label="Odstęp między zapytaniami"
              value={justjoin.request_delay_s}
              unit="s"
              width={80}
              invalid={Boolean(fieldError('justjoin.request_delay_s'))}
              required
              onChange={(v) => v !== null && set('justjoin', { request_delay_s: v })}
            />
          </Field>
          <Field
            label="Ponowienia przy błędzie"
            htmlFor="jj-retries"
            hint="Gdy serwis chwilowo nie odpowiada"
            error={fieldError('justjoin.max_retries')}
          >
            <NumberInput
              id="jj-retries"
              label="Ponowienia przy błędzie"
              value={justjoin.max_retries}
              unit="razy"
              width={80}
              invalid={Boolean(fieldError('justjoin.max_retries'))}
              required
              onChange={(v) => v !== null && set('justjoin', { max_retries: v })}
            />
          </Field>
        </Section>

        <Section
          {...sectionProps('advanced')}
          open={phone ? open === 'advanced' : advancedOpen}
          onToggle={phone ? () => setOpen(open === 'advanced' ? null : 'advanced') : () => setAdvancedOpen((v) => !v)}
          collapsible
          title="Zaawansowane"
          toml="[paths] [api]"
          badge="wymaga restartu serwera"
          summary="Ścieżki i adresy frontendu"
        >
          <p className="muted" style={{ fontSize: 12.5, paddingBottom: 6 }}>
            Ścieżki względne liczą się od folderu z config.toml. Po zapisaniu uruchom ponownie backend:{' '}
            <span className="mono">jobseeker serve</span> albo{' '}
            <span className="mono">docker compose restart backend</span>.
          </p>
          {(
            [
              ['cv_dir', 'Folder z CV', 'Używany jest najnowszy PDF', ''],
              ['cv_path', 'Konkretny plik CV', 'Zamiast najnowszego z folderu', 'puste = najnowszy PDF z folderu'],
              ['data_dir', 'Folder danych', 'Baza ofert i zbudowany profil', ''],
              ['overrides', 'Plik poprawek profilu', 'Edytowany na ekranie Profil', ''],
            ] as const
          ).map(([key, label, hint, placeholder]) => (
            <Field key={key} label={label} htmlFor={`path-${key}`} hint={hint} error={fieldError(`paths.${key}`)}>
              <input
                id={`path-${key}`}
                className={`input mono ${s.medium}`}
                placeholder={placeholder}
                value={paths[key] ?? ''}
                onChange={(e) =>
                  set('paths', { [key]: key === 'cv_path' ? e.target.value.trim() || null : e.target.value })
                }
              />
            </Field>
          ))}
          <Field
            label="Adresy frontendu (CORS)"
            hint="Strony, które mogą łączyć się z API z przeglądarki. Docker i serwer deweloperski działają bez zmian."
            error={fieldError('api.cors_origins')}
          >
            <TagInput
              label="Adresy frontendu"
              mono
              values={api.cors_origins}
              onChange={(cors_origins) => set('api', { cors_origins })}
            />
          </Field>
        </Section>

        <SaveBar
          changes={changes.length}
          preview={formatChanges(changes)}
          saving={save.isPending}
          saved={save.isSuccess && draft === null}
          error={save.error}
          collapseWhenClean
          onSave={onSave}
          onDiscard={() => {
            setDraft(null);
            save.reset();
          }}
          onReload={() => {
            save.reset();
            void config.refetch();
          }}
        />
      </div>
    </div>
  );
}

function Header({ file, showNav = false }: { file?: string; showNav?: boolean }) {
  return (
    <header className={s.topbar}>
      <div className={s.titleBlock}>
        <h1 className={s.title}>Ustawienia</h1>
        <span className="muted" style={{ fontSize: 12.5 }}>
          Zapisywane w{' '}
          <span className="mono" title={file}>
            {file ? file.split(/[\\/]/).slice(-2).join('/') : 'config.toml'}
          </span>{' '}
          – Twoje komentarze w pliku zostają
        </span>
      </div>
      {showNav ? (
        <nav className={s.sectionNav} aria-label="Sekcje ustawień">
          <a href="#matching">Dopasowanie</a>
          <a href="#ai">Model AI</a>
          <a href="#keys">Klucze API</a>
          <a href="#justjoin">JustJoin.it</a>
          <a href="#advanced">Zaawansowane</a>
        </nav>
      ) : null}
    </header>
  );
}

/** A settings card on desktop; on phones an accordion panel with a one-line summary. */
function Section({
  id,
  title,
  toml,
  aside,
  badge,
  summary,
  phone,
  open,
  collapsible = false,
  onToggle,
  children,
}: {
  id: SectionId;
  title: string;
  toml: string;
  aside?: string;
  badge?: string;
  summary: string;
  phone: boolean;
  open: boolean;
  collapsible?: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const headingId = `h-${id}`;
  if (phone || collapsible) {
    return (
      <section id={id} className={`card ${s.section} ${open ? s.sectionOpen : ''}`} aria-labelledby={headingId}>
        <button type="button" className={s.sectionToggle} aria-expanded={open} onClick={onToggle}>
          <span className={s.sectionToggleText}>
            <span className={s.sectionTitleRow}>
              <h2 id={headingId} className={s.sectionTitle}>
                {title}
              </h2>
              {phone ? null : <span className="mono muted">{toml}</span>}
              {badge ? <span className={s.badge}>{badge}</span> : null}
            </span>
            {phone ? <span className="muted">{summary}</span> : null}
          </span>
          {open ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
        </button>
        {open ? <div className={s.sectionBody}>{children}</div> : null}
      </section>
    );
  }
  return (
    <section id={id} className={`card ${s.section}`} aria-labelledby={headingId}>
      <div className={s.sectionTitleRow}>
        <h2 id={headingId} className={s.sectionTitle}>
          {title}
        </h2>
        <span className="mono muted">{toml}</span>
        {aside ? <span className={`muted ${s.sectionAside}`}>{aside}</span> : null}
      </div>
      <div className={s.sectionBody}>{children}</div>
    </section>
  );
}

function Ratio({
  id,
  label,
  value,
  example,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  example: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className={s.ratio}>
      <div className={s.ratioRow}>
        <label htmlFor={`ratio-${id}`}>{label}</label>
        <input
          id={`ratio-${id}`}
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <span className="mono">{percent(value)}</span>
      </div>
      <span className="muted" style={{ fontSize: 12 }}>
        {example}
      </span>
    </div>
  );
}
