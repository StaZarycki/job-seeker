import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { baseHandlers, config } from '../../test/fixtures';
import { renderApp } from '../../test/render';
import { server } from '../../test/server';

function captureConfigPuts(responses: ((body: unknown) => Response)[] = []) {
  const bodies: unknown[] = [];
  server.use(
    http.put('/api/config', async ({ request }) => {
      const body = await request.json();
      bodies.push(body);
      const respond = responses[bodies.length - 1];
      return respond ? respond(body) : HttpResponse.json({ ...config, version: 'v2', ...(body as object) });
    }),
  );
  return bodies;
}

describe('SettingsPage', () => {
  it('saves only the changed section, with the version it was read at', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const bodies = captureConfigPuts();
    renderApp('/settings');

    const topN = await screen.findByLabelText('Ocenianych ofert');
    await user.clear(topN);
    await user.type(topN, '30');
    expect(screen.getByText('Niezapisane zmiany: 1')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Pokaż zmiany' }));
    expect(screen.getByLabelText('Zmiany w config.toml')).toHaveTextContent('top_n = 20 → 30');

    await user.click(screen.getByRole('button', { name: 'Zapisz w config.toml' }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ version: 'v1', force: false, ai: { ...config.ai, top_n: 30 } });
    expect(await screen.findByText('Zapisano w config.toml · przed chwilą')).toBeInTheDocument();
  });

  it('asks before overwriting a config.toml changed meanwhile', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    const conflict = () =>
      HttpResponse.json({ detail: 'Plik config.toml zmienił się.', code: 'config_conflict' }, { status: 409 });
    const bodies = captureConfigPuts([conflict]);
    renderApp('/settings');

    await user.click(await screen.findByRole('button', { name: 'AI' }));
    await user.click(screen.getByRole('button', { name: 'Zapisz w config.toml' }));
    expect(await screen.findByText('config.toml zmienił się w międzyczasie.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Nadpisz plik' }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ force: true, matching: { mode: 'ai' } });
  });

  it('shows server validation errors next to the field', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    captureConfigPuts([
      () =>
        HttpResponse.json(
          { detail: 'Błędne dane', code: 'invalid_request', fields: { 'justjoin.page_size': 'Maksymalnie 100.' } },
          { status: 400 },
        ),
    ]);
    renderApp('/settings');

    const pageSize = await screen.findByLabelText('Ofert na stronę');
    await user.clear(pageSize);
    await user.type(pageSize, '150');
    await user.click(screen.getByRole('button', { name: 'Zapisz w config.toml' }));

    expect(await screen.findByText('Maksymalnie 100.')).toBeInTheDocument();
    expect(screen.getByText('Popraw 1 pole, żeby zapisać.')).toBeInTheDocument();
    expect(pageSize).toHaveAttribute('aria-invalid', 'true');
  });

  it('writes an API key without ever showing it', async () => {
    const user = userEvent.setup();
    let sent: unknown;
    server.use(
      ...baseHandlers(),
      http.put('/api/env-keys/:name', async ({ request, params }) => {
        sent = { name: params.name, body: await request.json() };
        return HttpResponse.json({ name: params.name, label: 'Zgodny z OpenAI', set: true, hint: '…9xyz' });
      }),
    );
    renderApp('/settings');

    const keys = await screen.findByRole('region', { name: 'Klucze API' });
    expect(await within(keys).findByText('…a3F9')).toBeInTheDocument();
    const buttons = within(keys).getAllByRole('button', { name: 'Dodaj' });
    await user.click(buttons[buttons.length - 1]!);
    const input = within(keys).getByLabelText('Zgodny z OpenAI: nowa wartość');
    expect(input).toHaveAttribute('type', 'password');
    await user.type(input, 'sk-secret-9xyz');
    await user.click(within(keys).getByRole('button', { name: 'Zapisz' }));

    await waitFor(() => expect(sent).toEqual({ name: 'OPENAI_API_KEY', body: { value: 'sk-secret-9xyz' } }));
    expect(await within(keys).findByText('…9xyz')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('sk-secret-9xyz')).not.toBeInTheDocument();
  });

  it('uses accordions on phones', async () => {
    const user = userEvent.setup();
    server.use(...baseHandlers());
    renderApp('/settings', { width: 390 });

    expect(await screen.findByRole('button', { name: /Dopasowanie/ })).toHaveAttribute('aria-expanded', 'true');
    const ai = screen.getByRole('button', { name: /Model AI/ });
    expect(ai).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('Ocenianych ofert')).not.toBeInTheDocument();

    await user.click(ai);
    expect(screen.getByLabelText('Ocenianych ofert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dopasowanie/ })).toHaveAttribute('aria-expanded', 'false');
  });
});
