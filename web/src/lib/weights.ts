import type { Schemas } from '../api/client';

export type RuleWeights = Schemas['RuleWeights'];

/** Fallback until GET /settings loads; mirrors RuleWeights defaults in backend/src/job_seeker/config.py. */
export const DEFAULT_WEIGHTS: RuleWeights = {
  skills: 0.45,
  title: 0.1,
  seniority: 0.15,
  location: 0.1,
  salary: 0.1,
  languages: 0.05,
  freshness: 0.05,
};
