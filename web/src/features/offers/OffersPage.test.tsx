import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { baseHandlers, matchResponse, RESULTS } from '../../test/fixtures';
import { renderApp } from '../../test/render';
import { server } from '../../test/server';

function matchesHandler(log: URLSearchParams[] = []) {
  return http.get('/api/matches', ({ request }) => {
    const params = new URL(request.url).searchParams;
    log.push(params);
    if (params.get('mode') === 'ai') {
      return HttpResponse.json(
        { detail: 'Brak klucza API Anthropic. Ustaw ANTHROPIC_API_KEY w pliku .env.', code: 'ai_not_configured' },
        { status: 400 },
      );
    }
    return HttpResponse.json(matchResponse());
  });
}

describe('OffersPage', () => {
  it('lists ranked offers and shows the first one in the side panel on wide screens', async () => {
    server.use(...baseHandlers(), matchesHandler());
    renderApp('/');

    const list = await screen.findByRole('region', { name: 'Ranking ofert' });
    expect(await within(list).findAllByRole('link')).toHaveLength(2);
    expect(within(list).getByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText('40', { exact: false })).toBeInTheDocument();

    const detail = await screen.findByRole('article', { name: 'Oferta: Backend Engineer' });
    expect(within(detail).getByText('Wynik Standard')).toBeInTheDocument();
    expect(within(detail).getByRole('link', { name: /Aplikuj w JustJoin.it/ })).toHaveAttribute(
      'href',
      RESULTS[0]!.offer.url,
    );
    expect(await within(detail).findByText('Opis oferty')).toBeInTheDocument(); // fetched on demand
  });

  it('explains a missing AI key and goes back to Standard mode', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers(), matchesHandler());
    const { router } = renderApp('/');

    await screen.findByText('Backend Engineer', { selector: 'div' });
    await user.click(screen.getByRole('button', { name: 'AI' }));

    expect(await screen.findByText('Tryb AI nie jest skonfigurowany.')).toBeInTheDocument();
    expect(screen.getByText('Backend Engineer', { selector: 'div' })).toBeInTheDocument(); // Standard ranking stays
    await user.click(screen.getByRole('button', { name: 'Wróć do trybu Standard' }));
    await waitFor(() => expect(router.state.location.search).toBe(''));
  });

  it('switches search presets; presets that need a sync are disabled', async () => {
    const user = userEvent.setup();
    const log: URLSearchParams[] = [];
    server.use(...baseHandlers(), matchesHandler(log));
    renderApp('/');

    await user.click(await screen.findByRole('button', { name: /Wyszukiwanie/ }));
    const options = screen.getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining('Domyślne'),
      expect.stringContaining('cpp'),
      expect.stringContaining('python'),
    ]);
    expect(options[2]).toBeDisabled();

    await user.click(options[1]!);
    await waitFor(() => expect(log.some((p) => p.get('search') === 'cpp')).toBe(true));
  });

  it('opens offer details as a full screen on phones', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers(), matchesHandler());
    const { router } = renderApp('/', { width: 390 });

    await user.click(await screen.findByRole('link', { name: /Senior Node.js Developer/ }));
    expect(router.state.location.pathname).toBe('/offers/justjoin%3Ab2');
    const detail = await screen.findByRole('article', { name: 'Oferta: Senior Node.js Developer' });
    await user.click(within(detail).getByRole('button', { name: 'Oferty' }));
    expect(router.state.location.pathname).toBe('/');
  });

  it('saves an offer', async () => {
    const user = userEvent.setup();
    let saved: unknown;
    server.use(
      ...baseHandlers(),
      matchesHandler(),
      http.put('/api/offers/:id/status', async ({ request, params }) => {
        saved = { id: params.id, body: await request.json() };
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp('/');

    const detail = await screen.findByRole('article', { name: 'Oferta: Backend Engineer' });
    await user.click(within(detail).getAllByRole('button', { name: /Zapisz/ })[0]!);
    await waitFor(() => expect(saved).toEqual({ id: 'justjoin:a1', body: { status: 'saved' } }));
  });

  it('marks an offer as visited when the job board link is opened, and as applied on request', async () => {
    const user = userEvent.setup();
    const updates: unknown[] = [];
    server.use(
      ...baseHandlers(),
      matchesHandler(),
      http.put('/api/offers/:id/activity', async ({ request, params }) => {
        updates.push({ id: params.id, body: await request.json() });
        return HttpResponse.json({ visited_at: '2026-10-07T10:00:00Z', applied_at: null });
      }),
    );
    renderApp('/');

    const detail = await screen.findByRole('article', { name: 'Oferta: Backend Engineer' });
    expect(within(detail).getByText('Jeszcze nie otwierana w JustJoin.it')).toBeInTheDocument();
    document.addEventListener('click', (event) => event.preventDefault(), { once: true }); // jsdom can't navigate
    await user.click(within(detail).getByRole('link', { name: /Aplikuj w JustJoin.it/ }));
    await waitFor(() => expect(updates).toEqual([{ id: 'justjoin:a1', body: { visited: true } }]));

    await user.click(within(detail).getByRole('button', { name: 'Oznacz jako aplikowaną' }));
    await waitFor(() => expect(updates).toHaveLength(2));
    expect(updates[1]).toEqual({ id: 'justjoin:a1', body: { applied: true } });
  });

  it('dims visited offers, tags them and filters by activity', async () => {
    const user = userEvent.setup();
    const log: URLSearchParams[] = [];
    const today = new Date().toISOString();
    const results = [
      { ...RESULTS[0]!, visited_at: today },
      { ...RESULTS[1]!, visited_at: today, applied_at: today },
    ];
    server.use(
      ...baseHandlers(),
      http.get('/api/matches', ({ request }) => {
        log.push(new URL(request.url).searchParams);
        return HttpResponse.json(matchResponse(results));
      }),
    );
    const { router } = renderApp('/');

    const list = await screen.findByRole('region', { name: 'Ranking ofert' });
    expect(await within(list).findByText('Odwiedzona dziś')).toBeInTheDocument();
    expect(within(list).getByText('Aplikowano dziś')).toBeInTheDocument();
    const detail = await screen.findByRole('article', { name: 'Oferta: Backend Engineer' });
    expect(within(detail).getByRole('button', { name: 'Oznacz jako nieodwiedzoną' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Bez odwiedzonych' }));
    await waitFor(() => expect(router.state.location.search).toBe('?activity=unvisited'));
    await waitFor(() => expect(log.at(-1)?.get('activity')).toBe('unvisited'));
    expect(screen.getByRole('button', { name: 'Bez odwiedzonych' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows company logos, or the initial when an offer has none', async () => {
    const logo = 'https://example.test/logo.png';
    const results = [{ ...RESULTS[0]!, offer: { ...RESULTS[0]!.offer, company_logo_url: logo } }, RESULTS[1]!];
    server.use(
      ...baseHandlers(),
      http.get('/api/matches', () => HttpResponse.json(matchResponse(results))),
    );
    renderApp('/');

    const list = await screen.findByRole('region', { name: 'Ranking ofert' });
    const [withLogo, withoutLogo] = await within(list).findAllByRole('link');
    expect(withLogo!.querySelector('img')).toHaveAttribute('src', logo);
    expect(withoutLogo!.querySelector('img')).toBeNull();
    expect(within(withoutLogo!).getByText(RESULTS[1]!.offer.company.charAt(0).toUpperCase())).toBeInTheDocument();
  });

  it('asks for a CV when the backend has none', async () => {
    server.use(
      ...baseHandlers(),
      http.get('/api/matches', () =>
        HttpResponse.json({ detail: "Nie znaleziono CV w folderze 'cv'.", code: 'cv_not_found' }, { status: 404 }),
      ),
    );
    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'Nie znaleziono CV' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Wgraj CV (PDF)' })).toHaveAttribute('href', '/profile');
  });
});
