import { describe, expect, it } from 'vitest';
import { hasWikiSummaries, loadWikiSummary, wikiSummaryBucket } from '../lib/wikiSummary';

describe('wikiSummary', () => {
  it('splits item IDs into buckets of 1000', () => {
    expect(wikiSummaryBucket(0)).toBe(0);
    expect(wikiSummaryBucket(999)).toBe(0);
    expect(wikiSummaryBucket(1000)).toBe(1);
    expect(wikiSummaryBucket(6164)).toBe(6);
  });

  it('only has bundled summaries for Chinese', () => {
    expect(hasWikiSummaries('zh-CN')).toBe(true);
    expect(hasWikiSummaries('en')).toBe(false);
  });

  it('loads a known item summary', async () => {
    const summary = await loadWikiSummary('zh-CN', 757);
    expect(summary?.title).toBeTruthy();
    expect(summary?.extract.length).toBeGreaterThan(10);
  });

  it('returns null for an item without an article', async () => {
    expect(await loadWikiSummary('zh-CN', 0)).toBeNull();
    expect(await loadWikiSummary('en', 757)).toBeNull();
  });
});
