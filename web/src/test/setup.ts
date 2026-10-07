import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './server';

/** jsdom has no layout: emulate window.matchMedia for min-/max-width queries at ``window.innerWidth``. */
function matchMedia(query: string): MediaQueryList {
  const width = window.innerWidth;
  const min = /min-width:\s*(\d+)px/.exec(query);
  const max = /max-width:\s*(\d+)px/.exec(query);
  const matches = (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
  return {
    matches,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  };
}

Object.defineProperty(window, 'matchMedia', { writable: true, value: matchMedia });

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  window.innerWidth = 1440;
});
afterAll(() => server.close());
