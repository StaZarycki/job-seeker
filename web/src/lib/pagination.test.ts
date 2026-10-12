import { describe, expect, it } from 'vitest';

import { pageItems, rangeLabel } from './pagination';

describe('pagination', () => {
  it('shows short lists whole and long ones around the current page', () => {
    expect(pageItems(2, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageItems(1, 45)).toEqual([1, 2, 3, 4, 5, 'gap', 45]);
    expect(pageItems(20, 45)).toEqual([1, 'gap', 19, 20, 21, 'gap', 45]);
    expect(pageItems(45, 45)).toEqual([1, 'gap', 41, 42, 43, 44, 45]);
  });

  it('labels the shown range', () => {
    expect(rangeLabel(20, 20)).toBe('21–40');
    expect(rangeLabel(40, 15)).toBe('41–55');
    expect(rangeLabel(0, 0)).toBe('0');
  });
});
