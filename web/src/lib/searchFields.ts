import type { SearchPreferences, Seniority, WorkplaceType } from '../api/client';

export type SearchKey = keyof SearchPreferences;
export type FieldType = 'sources' | 'categories' | 'level' | 'workplace' | 'tags' | 'switch' | 'number';

export interface SearchField {
  key: SearchKey;
  group: number;
  label: string;
  hint: string;
  type: FieldType;
  unit?: string;
  placeholder?: string;
}

export const SEARCH_GROUPS = ['Co pobierać', 'Filtry', 'Ocena'];

/** Every [search] field, in the order of the design (Wyszukiwania screen). */
export const SEARCH_FIELDS: SearchField[] = [
  { key: 'sources', group: 0, label: 'Źródła', hint: 'Serwisy, z których pobierane są oferty', type: 'sources' },
  {
    key: 'categories',
    group: 0,
    label: 'Kategorie',
    hint: 'Kategorie JustJoin.it · liczba ofert w serwisie',
    type: 'categories',
  },
  {
    key: 'experience_levels',
    group: 1,
    label: 'Poziom doświadczenia',
    hint: 'Automatycznie: Twój poziom w technologiach oferty i jeden wyżej',
    type: 'level',
  },
  { key: 'workplace', group: 1, label: 'Tryb pracy', hint: '', type: 'workplace' },
  { key: 'preferred_cities', group: 1, label: 'Preferowane miasta', hint: 'Premiowane w wyniku', type: 'tags' },
  {
    key: 'onsite_only_in_preferred_cities',
    group: 1,
    label: 'Hybryda i biuro tylko w tych miastach',
    hint: 'Odrzuca oferty hybrydowe i stacjonarne w innych miastach',
    type: 'switch',
  },
  {
    key: 'min_salary_pln_month',
    group: 1,
    label: 'Minimalne widełki',
    hint: 'Górne widełki · puste = bez limitu',
    type: 'number',
    unit: 'PLN/mies.',
    placeholder: 'np. 18000',
  },
  {
    key: 'max_offer_age_days',
    group: 1,
    label: 'Maks. wiek oferty',
    hint: 'Puste = bez limitu',
    type: 'number',
    unit: 'dni',
    placeholder: 'bez limitu',
  },
  {
    key: 'exclude_keywords',
    group: 1,
    label: 'Wykluczone słowa',
    hint: 'Całe słowa w tytule lub wymaganych umiejętnościach',
    type: 'tags',
  },
  {
    key: 'title_keywords',
    group: 2,
    label: 'Premiowane słowa w tytule',
    hint: 'Główne umiejętności z CV liczą się automatycznie',
    type: 'tags',
  },
  {
    key: 'avoid_title_keywords',
    group: 2,
    label: 'Słowa obniżające wynik',
    hint: 'Kara w wyniku, nie filtr – np. frontend, manager',
    type: 'tags',
  },
  {
    key: 'target_skills',
    group: 2,
    label: 'Technologie docelowe',
    hint: 'Na które się przebranżawiasz: częściowo zaliczane, przekazywane modelowi AI',
    type: 'tags',
  },
];

export const LEVELS: Seniority[] = ['intern', 'junior', 'mid', 'senior', 'manager', 'c_level'];

export const WORKPLACE_LABELS: Record<WorkplaceType, string> = {
  remote: 'Zdalnie',
  hybrid: 'Hybrydowo',
  office: 'Stacjonarnie',
};

export const SOURCE_LABELS: Record<string, string> = { justjoin: 'JustJoin.it' };

/** Same rule as the backend (config_store.PRESET_NAME / RESERVED_PRESET_NAMES). */
export function presetNameError(name: string, taken: string[]): string | null {
  if (!name) return 'Podaj nazwę profilu.';
  if (!/^[a-z0-9][a-z0-9_-]{0,39}$/.test(name)) return 'Tylko małe litery, cyfry, - i _ (do 40 znaków).';
  if (name === 'default' || name === 'new') return `Nazwa „${name}” jest zarezerwowana.`;
  if (taken.includes(name)) return 'Profil o tej nazwie już istnieje.';
  return null;
}

/** "nadpisuje 4 pola" */
export function overridesLabel(n: number): string {
  return `nadpisuje ${n} ${n === 1 ? 'pole' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'pola' : 'pól'}`;
}
