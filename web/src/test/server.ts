import { setupServer } from 'msw/node';

/** MSW server for component tests; each test registers the API handlers it needs with server.use(...). */
export const server = setupServer();
