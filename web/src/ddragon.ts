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

let names: Promise<Record<string, string>> | null = null;

function championNames(): Promise<Record<string, string>> {
  names ??= latestVersion()
    .then((v) => (v ? fetch(`https://ddragon.leagueoflegends.com/cdn/${v}/data/en_US/champion.json`) : null))
    .then((r) => (r?.ok ? r.json() : null))
    .then((json: { data: Record<string, { name: string }> } | null) =>
      Object.fromEntries(Object.entries(json?.data ?? {}).map(([id, c]) => [id, c.name])),
    )
    .catch(() => ({}));
  return names;
}

/** Display names ("Dr. Mundo" for DrMundo); a champion missing from the list keeps its id. */
export function useChampionNames(): (id: string) => string {
  const [table, setTable] = useState<Record<string, string>>({});
  useEffect(() => {
    championNames().then(setTable);
  }, []);
  return (id) => table[id] ?? id;
}
