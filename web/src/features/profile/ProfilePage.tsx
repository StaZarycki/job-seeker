import { useState, type DragEvent } from 'react';

import { ApiError, type CandidateProfile } from '../../api/client';
import { useProfile, useRebuildProfile, useSettings, useUploadCv } from '../../api/hooks';
import { useTheme } from '../../app/theme';
import { ApiErrorState } from '../../components/ApiErrorState';
import { FileIcon, MoonIcon, RefreshIcon, SunIcon, UploadIcon } from '../../components/icons';
import { Banner, Skeleton } from '../../components/ui';
import { countLabel, percent, years } from '../../lib/format';
import { OverridesForm } from './OverridesForm';
import s from './profile.module.css';

export function ProfilePage() {
  const profile = useProfile();
  const rebuild = useRebuildProfile();
  const [theme, toggleTheme] = useTheme();
  const [dismissed, setDismissed] = useState<string | null>(null);
  const data = profile.data;

  return (
    <div>
      <header className={s.topbar}>
        <div className={s.titleBlock}>
          <h1 className={s.title}>Profil</h1>
          {data ? (
            <span className="mono muted" style={{ fontSize: 12 }}>
              hash {data.profile_hash}
            </span>
          ) : null}
        </div>
        <div className={s.headerActions}>
          <button type="button" className={`icon-btn ${s.themeBtn}`} onClick={toggleTheme} aria-label="Zmień motyw">
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => rebuild.mutate()}
            disabled={rebuild.isPending || !data}
            aria-label="Przebuduj profil z CV"
          >
            <RefreshIcon size={15} />
            <span className={s.hidePhone}>{rebuild.isPending ? 'Przebudowuję…' : 'Przebuduj z CV'}</span>
          </button>
        </div>
      </header>

      <div className="page">
        {profile.error && !data ? (
          profile.error instanceof ApiError && profile.error.code === 'cv_not_found' ? (
            <>
              <Banner tone="warn">{profile.error.message}</Banner>
              <CvCard profile={null} />
            </>
          ) : (
            <ApiErrorState error={profile.error} onRetry={() => void profile.refetch()} />
          )
        ) : null}
        {data?.warning ? <Banner tone="warn">{data.warning}</Banner> : null}
        {data?.rebuilt && dismissed !== data.profile_hash ? (
          <Banner onDismiss={() => setDismissed(data.profile_hash)}>
            Profil przebudowany z <span className="mono">{data.profile.source_file}</span> – nowe lub zmienione CV.
            Oceny AI zostaną policzone od nowa.
          </Banner>
        ) : null}
        {rebuild.error ? <Banner tone="warn">{(rebuild.error as Error).message}</Banner> : null}

        {data ? (
          <div className={s.columns}>
            <div className={s.column}>
              <CvCard profile={data.profile} />
              <OverridesForm profile={data.profile} />
            </div>
            <div className={s.column}>
              <SkillsCard profile={data.profile} />
              <SkillYearsCard profile={data.profile} />
            </div>
          </div>
        ) : profile.isPending ? (
          <div className="card">
            <Skeleton width="40%" height={14} />
            <Skeleton width="70%" />
            <Skeleton width="55%" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

const LANGUAGE_NAMES: Record<string, string> = { pl: 'PL', en: 'EN', de: 'DE', ja: 'JA', fr: 'FR', es: 'ES' };

function CvCard({ profile }: { profile: CandidateProfile | null }) {
  const upload = useUploadCv();
  const [dragging, setDragging] = useState(false);

  const send = (file: File | undefined) => {
    if (file) upload.mutate(file);
  };
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    send(event.dataTransfer.files[0]);
  };

  return (
    <section className="card" aria-label="CV">
      <h2 className="card-title">CV</h2>
      {profile ? (
        <>
          <dl className={s.facts}>
            <div>
              <dt>Stanowisko</dt>
              <dd>{profile.headline ?? '—'}</dd>
            </div>
            <div>
              <dt>Lokalizacja</dt>
              <dd>{profile.location ?? '—'}</dd>
            </div>
            <div>
              <dt>Doświadczenie</dt>
              <dd>
                {countLabel(profile.years_of_experience, ['rok', 'lata', 'lat'])} · {profile.seniority}
              </dd>
            </div>
            <div>
              <dt>Języki</dt>
              <dd>
                {Object.entries(profile.languages)
                  .map(([code, level]) => `${LANGUAGE_NAMES[code] ?? code.toUpperCase()} ${level}`)
                  .join(' · ') || '—'}
              </dd>
            </div>
          </dl>
          <div className={s.fileRow}>
            <FileIcon size={18} strokeWidth={1.6} />
            <div style={{ flex: '1 1 auto', minWidth: 0 }}>
              <div className="mono" style={{ fontSize: 13 }}>
                {profile.source_file}
              </div>
              <div className="muted" style={{ fontSize: 12 }}>
                cv/ · najnowszy PDF w folderze
              </div>
            </div>
          </div>
        </>
      ) : null}
      <label
        className={`${s.dropzone} ${dragging ? s.dropzoneActive : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <UploadIcon size={22} strokeWidth={1.6} style={{ color: 'var(--accent)' }} />
        <span style={{ fontWeight: 500 }}>
          {upload.isPending ? (
            'Wgrywam i przebudowuję profil…'
          ) : (
            <>
              <span className={s.hidePhone}>Przeciągnij nowe CV albo wybierz plik</span>
              <span className={s.showPhone}>Wybierz nowe CV</span>
            </>
          )}
        </span>
        <span className="muted" style={{ fontSize: 12.5 }}>
          PDF do 10 MB · profil przebuduje się automatycznie, poprawki zostaną zachowane
        </span>
        <input
          type="file"
          accept="application/pdf"
          className="visually-hidden"
          disabled={upload.isPending}
          onChange={(e) => {
            send(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
      </label>
      {upload.error ? <p className={s.error}>{(upload.error as Error).message}</p> : null}
    </section>
  );
}

function SkillsCard({ profile }: { profile: CandidateProfile }) {
  const core = profile.skills.filter((sk) => sk.weight >= 1);
  const other = profile.skills.filter((sk) => sk.weight < 1);
  return (
    <section className="card" aria-label="Umiejętności">
      <h2 className="card-title">Umiejętności</h2>
      <div className={s.skillGroup}>
        <div className="section-hint">Główne · waga 1.0</div>
        <div className={s.chips}>
          {core.map((sk) => (
            <span key={sk.name} className={s.coreChip}>
              {sk.name}
            </span>
          ))}
        </div>
      </div>
      <div className={s.skillGroup}>
        <div className="section-hint">Pozostałe</div>
        <div className={s.chips}>
          {other.map((sk) => (
            <span key={sk.name} className={s.otherChip}>
              {sk.name} <span className="mono muted">{sk.weight.toFixed(2)}</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function SkillYearsCard({ profile }: { profile: CandidateProfile }) {
  const settings = useSettings();
  const entries = Object.entries(profile.skill_years).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, profile.years_of_experience, ...entries.map(([, v]) => v));
  const declared = profile.skills
    .filter((sk) => sk.weight >= 1 && !(sk.name in profile.skill_years))
    .map((sk) => sk.name);
  const declaredRatio = settings.data?.experience.declared_ratio ?? 0.5;
  const transferRatio = settings.data?.experience.transfer_ratio ?? 0.35;

  return (
    <section className="card" aria-label="Lata doświadczenia per technologia">
      <div>
        <h2 className="card-title">Lata per technologia</h2>
        <div className="section-hint">z pozycji w sekcji Experience</div>
      </div>
      <div className={s.yearBars}>
        {entries.map(([name, value]) => (
          <div className={s.yearBar} key={name}>
            <span className={s.yearName}>{name}</span>
            <div className={s.track}>
              <div className={s.fill} style={{ width: `${(value / max) * 100}%` }} />
            </div>
            <span className="mono" style={{ textAlign: 'right' }}>
              {years(value)}
            </span>
          </div>
        ))}
      </div>
      <div className="note">
        {declared.length ? (
          <>
            {declared.join(', ')} {declared.length === 1 ? 'jest' : 'są'} w CV, ale bez stanowiska – liczę je jako{' '}
            {percent(declaredRatio)} stażu (~{years(profile.years_of_experience * declaredRatio)} roku).{' '}
          </>
        ) : null}
        W technologii spoza CV ogólny staż przenosi się w {percent(transferRatio)}, np. C++ ≈{' '}
        {years(profile.years_of_experience * transferRatio)} roku.
      </div>
    </section>
  );
}
