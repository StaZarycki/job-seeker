/** What changed between the loaded settings and the edited draft, as config.toml-like lines. */

export interface Change {
  section: string;
  key: string;
  from: unknown;
  to: unknown;
}

function flatten(value: unknown, path: string[], out: Map<string, unknown>): void {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) flatten(child, [...path, key], out);
  } else {
    out.set(path.join('.'), value);
  }
}

export function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** ``prefix`` names the TOML table of the compared objects, e.g. "searches.cpp". */
export function diffValues(before: object, after: object, prefix = ''): Change[] {
  const a = new Map<string, unknown>();
  const b = new Map<string, unknown>();
  flatten(before, [], a);
  flatten(after, [], b);
  const changes: Change[] = [];
  for (const path of new Set([...a.keys(), ...b.keys()])) {
    if (sameValue(a.get(path), b.get(path))) continue;
    const parts = (prefix ? `${prefix}.${path}` : path).split('.');
    const key = parts.pop() ?? path;
    changes.push({ section: parts.join('.'), key, from: a.get(path), to: b.get(path) });
  }
  return changes;
}

function tomlValue(value: unknown): string {
  if (value === undefined || value === null) return '—';
  return JSON.stringify(value).replace(/,/g, ', ');
}

/** "[ai]\n  top_n = 20  →  30" blocks, one per table. */
export function formatChanges(changes: Change[]): string {
  const bySection = new Map<string, string[]>();
  for (const change of changes) {
    const lines = bySection.get(change.section) ?? [];
    lines.push(`  ${change.key} = ${tomlValue(change.from)}  →  ${tomlValue(change.to)}`);
    bySection.set(change.section, lines);
  }
  return [...bySection.entries()].map(([section, lines]) => `[${section}]\n${lines.join('\n')}`).join('\n\n');
}
