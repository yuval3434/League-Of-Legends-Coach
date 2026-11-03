// The selected player, loaded once per page. The URL holds only a PUUID; the
// server decides everything else about them, including which benchmarks fit.

import { useEffect, useState } from "react";

import { api, type Player } from "./api";
import { useRoute } from "./router";

export function usePlayer(): { puuid: string | null; player: Player | null; error: string | null } {
  const puuid = useRoute().params.get("player");
  const [player, setPlayer] = useState<Player | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setPlayer(null);
    setError(null);
    api.player(puuid).then(setPlayer).catch((e: Error) => setError(e.message));
  }, [puuid]);
  return { puuid, player, error };
}

/** The cohort a player is measured against first: their peers, else a target, else none. */
export function mainCohort(player: Player): "silver" | "emerald" | null {
  if (player.benchmarks.silver === null) return "silver";
  if (player.benchmarks.emerald === null) return "emerald";
  return null;
}
