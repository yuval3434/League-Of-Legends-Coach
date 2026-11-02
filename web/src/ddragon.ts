// Champion icons from Riot's Data Dragon, at its current version.

import { useEffect, useState } from "react";

const VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json";

let cached: Promise<string | null> | null = null;

function latestVersion(): Promise<string | null> {
  cached ??= fetch(VERSIONS)
    .then((r) => (r.ok ? r.json() : null))
    .then((versions: string[] | null) => versions?.[0] ?? null)
    .catch(() => null);
  return cached;
}

/** The icon URL, or null while loading or if Data Dragon can't be reached. */
export function useChampionIcon(champion: string): string | null {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    latestVersion().then(setVersion);
  }, []);
  // Match data names champions the way Data Dragon's file names do.
  return version
    ? `https://ddragon.leagueoflegends.com/cdn/${version}/img/champion/${champion}.png`
    : null;
}
