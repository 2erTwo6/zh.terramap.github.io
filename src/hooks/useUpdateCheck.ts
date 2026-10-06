import { useEffect, useState } from 'react';
import { getNativeVersion, isNative } from '../lib/native';
import { compareVersions, type VersionInfo } from '../lib/version';

/** How often to poll for a newer version, in milliseconds. */
const CHECK_INTERVAL_MS = 30 * 60 * 1000;

/**
 * How often a page load is allowed to hit the network for version.json, in
 * milliseconds. Repeated loads within this window reuse a cached response
 * instead of re-fetching, which keeps reloads from costing a CDN request each.
 */
const CHECK_THROTTLE_MS = 5 * 60 * 1000;

const STORAGE_KEY = 'terramap:version-check';

export type UpdateType = 'web' | 'native';

/** Returns the previously stored VersionInfo if it is still fresh enough. */
function readThrottled(): VersionInfo | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const { at, info } = JSON.parse(raw) as { at: number; info: VersionInfo };
    if (typeof at !== 'number' || Date.now() - at > CHECK_THROTTLE_MS) return null;
    return info;
  } catch {
    return null;
  }
}

function writeThrottled(info: VersionInfo): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ at: Date.now(), info }));
  } catch {
    // Ignore — storage can be unavailable (private mode, quota).
  }
}

async function fetchVersionInfo(): Promise<VersionInfo | null> {
  const cached = readThrottled();
  if (cached) return cached;

  try {
    // No `ts` cache-buster and no `no-store`: version.json is served with
    // `max-age=0, must-revalidate`, so the browser can revalidate it with a
    // cheap conditional request, and the throttle above usually skips it.
    const url = `${__BASE_URL__}version.json`;
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) return null;
    const info = (await res.json()) as VersionInfo;
    writeThrottled(info);
    return info;
  } catch {
    return null;
  }
}

/**
 * Polls the deployed version.json and reports when an update is available.
 *
 * - Web: compares the deployed commit hash against the one baked into this
 *   build. A mismatch means a newer build has been deployed → reload to update.
 * - Native: the app loads its frontend live from the site, so only the native
 *   shell can be out of date. Compares the latest released native version
 *   against the installed one → download the new app.
 *
 * Returns the update type once detected, otherwise null.
 */
export function useUpdateCheck(): UpdateType | null {
  const [updateType, setUpdateType] = useState<UpdateType | null>(null);

  useEffect(() => {
    let cancelled = false;
    const native = isNative();

    const check = async () => {
      const info = await fetchVersionInfo();
      if (!info || cancelled) return;

      if (native) {
        try {
          const current = await getNativeVersion();
          if (!cancelled && info.nativeVersion && compareVersions(info.nativeVersion, current) > 0) {
            setUpdateType('native');
          }
        } catch {
          // Ignore — can't determine the installed native version.
        }
      } else if (info.commit && info.commit !== __GIT_HASH__) {
        setUpdateType('web');
      }
    };

    void check();
    const interval = setInterval(() => void check(), CHECK_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void check();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);

    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, []);

  return updateType;
}
