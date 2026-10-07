import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { ApiError } from '../api/client';
import { FileIcon } from './icons';
import { StateCard } from './ui';

/** Full-size state for a failed request, with the next step for each known error code. */
export function ApiErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const retry = onRetry ? (
    <button type="button" className="btn btn-primary" onClick={onRetry}>
      Spróbuj ponownie
    </button>
  ) : null;

  let tag: string | undefined;
  let title = 'Coś poszło nie tak';
  let icon: ReactNode = null;
  let actions: ReactNode = retry;

  switch (apiError?.code) {
    case 'cv_not_found':
      tag = '404 · brak CV';
      title = 'Nie znaleziono CV';
      icon = <FileIcon size={34} strokeWidth={1.5} style={{ color: 'var(--warn)' }} />;
      actions = (
        <Link to="/profile" className="btn btn-primary">
          Wgraj CV (PDF)
        </Link>
      );
      break;
    case 'source_unavailable':
      tag = '502 · źródło ofert';
      title = 'Serwis z ofertami nie odpowiada';
      break;
    case 'network':
      tag = 'brak połączenia';
      title = 'Brak połączenia z backendem';
      break;
    case 'invalid_request':
      tag = '400';
      title = 'Niepoprawne zapytanie';
      break;
    default:
      tag = apiError ? String(apiError.status) : undefined;
  }

  return (
    <StateCard tag={tag} icon={icon} title={title} actions={actions}>
      {error instanceof Error ? error.message : String(error)}
    </StateCard>
  );
}
