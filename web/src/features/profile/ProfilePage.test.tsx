import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { baseHandlers, profileResponse } from '../../test/fixtures';
import { renderApp } from '../../test/render';
import { server } from '../../test/server';

describe('ProfilePage', () => {
  it('shows the profile parsed from the CV', async () => {
    server.use(...baseHandlers());
    renderApp('/profile');

    expect(await screen.findByText('cv.pdf', { selector: 'div' })).toBeInTheDocument();
    const years = screen.getByRole('region', { name: 'Lata doświadczenia per technologia' });
    expect(within(years).getByText('node.js')).toBeInTheDocument();
    // python is listed in the CV without a position -> explained as half of the total experience
    expect(within(years).getByText(/python jest w CV, ale bez stanowiska/)).toBeInTheDocument();
  });

  it('saves manual corrections', async () => {
    const user = userEvent.setup();
    let body: Record<string, unknown> | undefined;
    server.use(
      ...baseHandlers(),
      http.put('/api/profile/overrides', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(profileResponse);
      }),
    );
    renderApp('/profile');

    const form = await screen.findByRole('region', { name: 'Ręczne poprawki' });
    await user.click(await within(form).findByRole('button', { name: '+ Dodaj technologię' }));
    await user.type(within(form).getByRole('textbox', { name: 'Technologia' }), 'python');
    await user.type(within(form).getByRole('spinbutton', { name: 'Lata: python' }), '2');
    await user.type(within(form).getByRole('textbox', { name: 'Dodaj umiejętności' }), 'Kafka, Kubernetes');
    await user.click(within(form).getByRole('button', { name: 'Zapisz poprawki' }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body).toMatchObject({ skill_years: { python: 2 }, add_skills: ['Kafka', 'Kubernetes'], seniority: null });
    expect(await within(form).findByText('Zapisano – profil zaktualizowany.')).toBeInTheDocument();
  });

  it('uploads a new CV', async () => {
    const user = userEvent.setup();
    let uploaded: { size: number; type: string } | undefined;
    server.use(
      ...baseHandlers(),
      http.post('/api/profile/cv', async ({ request }) => {
        // jsdom drops the file name in multipart bodies, so check the part itself.
        const file = (await request.formData()).get('file') as Blob;
        uploaded = { size: file.size, type: file.type };
        return HttpResponse.json({ ...profileResponse, rebuilt: true });
      }),
    );
    const { container } = renderApp('/profile');

    await screen.findByText('cv.pdf', { selector: 'div' });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['%PDF-1.4'], 'nowe.pdf', { type: 'application/pdf' }));

    await waitFor(() => expect(uploaded).toEqual({ size: 8, type: 'application/pdf' }));
    expect(await screen.findByText(/nowe lub zmienione CV/)).toBeInTheDocument();
  });
});
