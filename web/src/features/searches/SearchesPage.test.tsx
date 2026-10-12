import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { baseHandlers, preferences } from '../../test/fixtures';
import { renderApp } from '../../test/render';
import { server } from '../../test/server';

function capture(method: 'put' | 'delete', path: string) {
  const calls: { url: string; body: unknown }[] = [];
  const handler = method === 'put' ? http.put : http.delete;
  server.use(
    handler(path, async ({ request }) => {
      calls.push({ url: request.url, body: method === 'put' ? await request.json() : null });
      return HttpResponse.json({ version: 'v2', restart_required: false });
    }),
  );
  return calls;
}

describe('SearchesPage', () => {
  it('overrides an inherited field of a preset and saves only the overrides', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const calls = capture('put', '/api/searches/:name');
    renderApp('/searches/cpp');

    const editor = await screen.findByRole('region', { name: 'Edycja profilu cpp' });
    expect(within(editor).getByRole('button', { name: 'Dziedzicz Kategorie z Domyślnych' })).toBeInTheDocument();
    // Inherited: shows the default's value, locked until "Nadpisz".
    expect(within(editor).getByRole('button', { name: 'Usuń Java' })).toBeDisabled();

    await user.click(within(editor).getByRole('button', { name: 'Nadpisz Wykluczone słowa' }));
    await user.click(within(editor).getByRole('button', { name: 'Usuń Java' }));
    await user.type(within(editor).getByLabelText('Dodaj: Wykluczone słowa'), 'C#{Enter}');
    await user.click(within(editor).getByRole('button', { name: 'Zapisz w config.toml' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.url).toMatch(/\/api\/searches\/cpp$/);
    expect(calls[0]!.body).toEqual({
      version: 'v1',
      force: false,
      overrides: { categories: ['c'], target_skills: ['C++'], exclude_keywords: ['C#'] },
      create: false,
      rename_to: null,
    });
  });

  it('creates a new preset from the defaults', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const calls = capture('put', '/api/searches/:name');
    const { router } = renderApp('/searches/new');

    const editor = await screen.findByRole('region', { name: 'Edycja profilu nowego' });
    const create = within(editor).getByRole('button', { name: 'Utwórz profil' });
    await user.type(within(editor).getByLabelText('Nazwa profilu'), 'cpp');
    expect(within(editor).getByText('Profil o tej nazwie już istnieje.')).toBeInTheDocument();
    expect(create).toBeDisabled();

    await user.clear(within(editor).getByLabelText('Nazwa profilu'));
    await user.type(within(editor).getByLabelText('Nazwa profilu'), 'go');
    await user.click(within(editor).getByRole('button', { name: 'Nadpisz Technologie docelowe' }));
    await user.type(within(editor).getByLabelText('Dodaj: Technologie docelowe'), 'Go{Enter}');
    await user.click(create);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.url).toMatch(/\/api\/searches\/go$/);
    expect(calls[0]!.body).toMatchObject({ create: true, overrides: { target_skills: ['Go'] } });
    await waitFor(() => expect(router.state.location.pathname).toBe('/searches/go'));
  });

  it('edits the default search on desktop', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const calls = capture('put', '/api/searches/default');
    renderApp('/searches');

    const editor = await screen.findByRole('region', { name: 'Edycja: Domyślne' });
    expect(within(editor).queryByRole('button', { name: /Nadpisz/ })).not.toBeInTheDocument();
    await user.click(within(editor).getByRole('switch', { name: 'Hybryda i biuro tylko w tych miastach' }));
    await user.click(within(editor).getByRole('button', { name: 'Zapisz w config.toml' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.body).toEqual({
      version: 'v1',
      force: false,
      preferences: { ...preferences, onsite_only_in_preferred_cities: false },
    });
  });

  it('deletes a preset after confirmation', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const calls = capture('delete', '/api/searches/:name');
    const { router } = renderApp('/searches/python');

    const editor = await screen.findByRole('region', { name: 'Edycja profilu python' });
    await user.click(within(editor).getByRole('button', { name: 'Usuń' }));
    await user.click(within(editor).getByRole('button', { name: 'Usuń profil' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.url).toMatch(/\/api\/searches\/python\?version=v1&force=false$/);
    await waitFor(() => expect(router.state.location.pathname).toBe('/searches'));
  });

  it('lists searches on phones and edits them full screen', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const { router } = renderApp('/searches', { width: 390 });

    expect(await screen.findByRole('button', { name: /Domyślne/ })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.queryByRole('region', { name: /Edycja/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /cpp/ }));
    await user.click(screen.getByRole('link', { name: 'Edytuj' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/searches/cpp'));
    const editor = await screen.findByRole('region', { name: 'Edycja profilu cpp' });
    expect(within(editor).getByRole('link', { name: /Wyszukiwania/ })).toHaveAttribute('href', '/searches');
  });
});
