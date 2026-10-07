import { QueryClient } from '@tanstack/react-query';
import { Link, type RouteObject } from 'react-router';

import { shouldRetry } from '../api/hooks';
import { StateCard } from '../components/ui';
import { OffersPage } from '../features/offers/OffersPage';
import { ProfilePage } from '../features/profile/ProfilePage';
import { SearchesPage } from '../features/searches/SearchesPage';
import { SourcesPage } from '../features/sources/SourcesPage';
import { AppShell } from './AppShell';

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <OffersPage /> },
      { path: 'offers/:offerId', element: <OffersPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: 'searches', element: <SearchesPage /> },
      { path: 'sources', element: <SourcesPage /> },
      {
        path: '*',
        element: (
          <div className="page">
            <StateCard
              tag="404"
              title="Nie ma takiej strony"
              actions={
                <Link to="/" className="btn btn-primary">
                  Przejdź do ofert
                </Link>
              }
            />
          </div>
        ),
      },
    ],
  },
];

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, refetchOnWindowFocus: false },
    },
  });
}
