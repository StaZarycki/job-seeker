import type { ComponentType } from 'react';
import { Link, Outlet, useLocation } from 'react-router';

import { useProfile } from '../api/hooks';
import { BriefcaseIcon, DatabaseIcon, MoonIcon, SlidersIcon, SunIcon, UserIcon } from '../components/icons';
import { countLabel } from '../lib/format';
import s from './AppShell.module.css';
import { useTheme } from './theme';

const NAV: { to: string; label: string; icon: ComponentType<{ size?: number }> }[] = [
  { to: '/', label: 'Oferty', icon: BriefcaseIcon },
  { to: '/profile', label: 'Profil', icon: UserIcon },
  { to: '/searches', label: 'Wyszukiwania', icon: SlidersIcon },
  { to: '/sources', label: 'Źródła', icon: DatabaseIcon },
];

/** Offers live at "/" and "/offers/:id", so "Oferty" is active on both. */
function isActive(to: string, pathname: string): boolean {
  if (to === '/') return pathname === '/' || pathname.startsWith('/offers');
  return pathname.startsWith(to);
}

export function AppShell() {
  const [theme, toggleTheme] = useTheme();
  const { pathname, search } = useLocation();
  const profile = useProfile();
  const p = profile.data?.profile;
  // Keep the chosen search preset / mode when switching back to the offers tab.
  const offersHref = (to: string) => (to === '/' && isActive('/', pathname) ? `/${search}` : to);

  return (
    <div className={s.shell}>
      <nav className={s.sidebar} aria-label="Główna nawigacja">
        <div className={s.brand}>Job Seeker</div>
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = isActive(to, pathname);
          return (
            <Link
              key={to}
              to={offersHref(to)}
              aria-current={active ? 'page' : undefined}
              className={`${s.navLink} ${active ? s.navLinkActive : ''}`}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
        <div className={s.sidebarFooter}>
          {p ? (
            <Link to="/profile" className={s.sidebarProfile}>
              <span style={{ fontWeight: 500 }}>{p.headline ?? 'Profil'}</span>
              <span className={s.sidebarSub}>
                {p.location?.split(',')[0] ?? '—'} ·{' '}
                {countLabel(Math.round(p.years_of_experience), ['rok', 'lata', 'lat'])} · {p.seniority}
              </span>
              <span className={s.sidebarFile} title={p.source_file ?? ''}>
                {p.source_file}
              </span>
            </Link>
          ) : (
            <span className={s.sidebarSub}>Brak profilu</span>
          )}
          <button type="button" className={s.themeToggle} onClick={toggleTheme}>
            {theme === 'dark' ? <SunIcon size={15} /> : <MoonIcon size={15} />}
            {theme === 'dark' ? 'Jasny motyw' : 'Ciemny motyw'}
          </button>
        </div>
      </nav>

      <div className={s.content}>
        <Outlet />
      </div>

      <nav className={s.tabs} aria-label="Nawigacja dolna">
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = isActive(to, pathname);
          return (
            <Link
              key={to}
              to={offersHref(to)}
              aria-current={active ? 'page' : undefined}
              className={`${s.tab} ${active ? s.tabActive : ''}`}
            >
              <Icon size={20} />
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
