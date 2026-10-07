import { describe, expect, it } from 'vitest';

import { offer } from '../test/fixtures';
import { citiesLabel, countLabel, formatNumber, plural, salaryText, scoreTone, years } from './format';

describe('format', () => {
  it('groups thousands with spaces', () => {
    expect(formatNumber(25713)).toBe('25 713');
    expect(formatNumber(999)).toBe('999');
    expect(formatNumber(1234567.4)).toBe('1 234 567');
  });

  it('picks Polish plural forms', () => {
    const forms: [string, string, string] = ['oferta', 'oferty', 'ofert'];
    expect([1, 2, 4, 5, 12, 14, 22, 25, 112].map((n) => plural(n, forms))).toEqual([
      'oferta',
      'oferty',
      'oferty',
      'ofert',
      'ofert',
      'ofert',
      'oferty',
      'ofert',
      'ofert',
    ]);
    expect(countLabel(2446, forms)).toBe('2 446 ofert');
  });

  it('shows the best salary with its contract', () => {
    const o = offer('x', 'X', {
      salaries: [
        {
          contract: 'b2b',
          min_pln_month: 15000,
          max_pln_month: 18000,
          gross: false,
          original_currency: 'PLN',
          original_unit: 'hour',
          original_min: 90,
          original_max: 110,
        },
        {
          contract: 'permanent',
          min_pln_month: 16000,
          max_pln_month: 21000,
          gross: true,
          original_currency: 'PLN',
          original_unit: 'month',
          original_min: null,
          original_max: null,
        },
      ],
    });
    expect(salaryText(o)).toEqual({ range: '16 000 – 21 000', contract: 'UoP, brutto' });
    expect(salaryText(offer('y', 'Y', { salaries: [] }))).toBeNull();
  });

  it('shortens long city lists', () => {
    const o = offer('x', 'X', {
      locations: ['Warszawa', 'Kraków', 'Wrocław', 'Poznań', 'Gdańsk'].map((city) => ({ city, street: null })),
    });
    expect(citiesLabel(o)).toBe('Warszawa, Kraków, Wrocław +2');
  });

  it('maps scores to tones and rounds years', () => {
    expect([95, 80, 79, 60, 59].map(scoreTone)).toEqual(['high', 'high', 'mid', 'mid', 'low']);
    expect(years(2.94)).toBe('2.9');
    expect(years(4)).toBe('4');
    expect(years(null)).toBe('?');
  });
});
