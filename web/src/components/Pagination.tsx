import { Link } from 'react-router';

import { pageItems } from '../lib/pagination';
import { ChevronLeftIcon } from './icons';
import s from './Pagination.module.css';

/**
 * Page links under a list. Real links (``hrefFor``), so pages can be opened in a new tab and the back button
 * works; ``compact`` (phones) shows only previous / "2 z 45" / next.
 */
export function Pagination({
  page,
  pageCount,
  hrefFor,
  compact = false,
}: {
  page: number;
  pageCount: number;
  hrefFor: (page: number) => string;
  compact?: boolean;
}) {
  if (pageCount <= 1) return null;
  const toTop = () => window.scrollTo({ top: 0 });
  const prev = page > 1 ? page - 1 : null;
  const next = page < pageCount ? page + 1 : null;

  return (
    <nav className={`${s.pagination} ${compact ? s.compact : ''}`} aria-label="Strony rankingu">
      {prev ? (
        <Link to={hrefFor(prev)} className={`btn ${s.step}`} rel="prev" onClick={toTop}>
          <ChevronLeftIcon size={16} />
          {compact ? 'Poprzednia' : <span className="visually-hidden">Poprzednia strona</span>}
        </Link>
      ) : (
        <span className={`btn ${s.step} ${s.disabled}`} aria-hidden="true">
          <ChevronLeftIcon size={16} />
          {compact ? 'Poprzednia' : null}
        </span>
      )}

      {compact ? (
        <span className={`mono ${s.position}`} aria-current="page">
          {page} z {pageCount}
        </span>
      ) : (
        <ol className={s.pages}>
          {pageItems(page, pageCount).map((item, i) =>
            item === 'gap' ? (
              <li key={`gap-${i}`} className={s.gap} aria-hidden="true">
                …
              </li>
            ) : (
              <li key={item}>
                <Link
                  to={hrefFor(item)}
                  className={`${s.page} ${item === page ? s.current : ''}`}
                  aria-current={item === page ? 'page' : undefined}
                  aria-label={`Strona ${item}`}
                  onClick={toTop}
                >
                  {item}
                </Link>
              </li>
            ),
          )}
        </ol>
      )}

      {next ? (
        <Link to={hrefFor(next)} className={`btn ${s.step}`} rel="next" onClick={toTop}>
          {compact ? 'Następna' : <span className="visually-hidden">Następna strona</span>}
          <ChevronLeftIcon size={16} className={s.flip} />
        </Link>
      ) : (
        <span className={`btn ${s.step} ${s.disabled}`} aria-hidden="true">
          {compact ? 'Następna' : null}
          <ChevronLeftIcon size={16} className={s.flip} />
        </span>
      )}
    </nav>
  );
}
