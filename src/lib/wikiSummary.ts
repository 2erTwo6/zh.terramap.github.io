/// <reference types="vite/client" />
// Intro summaries of item articles from the Terraria Wiki, bundled for offline use.
// Only languages with generated data (currently zh-CN) resolve; everything else keeps
// opening the wiki in a browser. Regenerate with scripts/sync-wiki.py.
export interface WikiSummary {
  title: string;
  extract: string;
}

interface WikiSummaryEntry {
  t: string;
  extract: string;
}

type WikiSummaryTable = Record<string, WikiSummaryEntry>;

const BUCKET_SIZE = 1000;

const loaders = import.meta.glob<WikiSummaryTable>('../i18n/wiki/*.json', { import: 'default' });
const cache = new Map<string, Promise<WikiSummaryTable | null>>();

/** Item IDs are split into buckets so a click only downloads the part it needs. */
export function wikiSummaryBucket(itemId: number): number {
  return Math.floor(Math.max(0, itemId) / BUCKET_SIZE);
}

export function hasWikiSummaries(language: string): boolean {
  return `../i18n/wiki/${language}-0.json` in loaders;
}

export async function loadWikiSummary(language: string, itemId: number): Promise<WikiSummary | null> {
  const path = `../i18n/wiki/${language}-${wikiSummaryBucket(itemId)}.json`;
  const loader = loaders[path];
  if (!loader) return null;
  let pending = cache.get(path);
  if (!pending) {
    const created = loader().catch(() => null);
    cache.set(path, created);
    pending = created;
  }
  const table = await pending;
  const entry = table?.[String(itemId)];
  return entry ? { title: entry.t, extract: entry.extract } : null;
}
