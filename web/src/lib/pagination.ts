export type PageItem = number | 'gap';

/** "1 … 4 5 6 … 45": first, last and the pages around the current one; short lists are shown whole. */
export function pageItems(page: number, pageCount: number, around = 1): PageItem[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1);
  const start = Math.max(2, Math.min(page - around, pageCount - 2 - 2 * around));
  const end = Math.min(pageCount - 1, Math.max(page + around, 3 + 2 * around));
  const items: PageItem[] = [1];
  if (start > 2) items.push('gap');
  for (let p = start; p <= end; p++) items.push(p);
  if (end < pageCount - 1) items.push('gap');
  items.push(pageCount);
  return items;
}

/** "21–40" for page 2 of 20 per page (the last page may be shorter). */
export function rangeLabel(offset: number, shown: number): string {
  return shown === 0 ? '0' : `${offset + 1}–${offset + shown}`;
}
