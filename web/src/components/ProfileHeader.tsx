import type { Coverage, Player } from "../api";
import { useChampionNames } from "../ddragon";
import { ChampionIcon } from "./ChampionIcon";

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const ROLES: Record<string, string> = { TOP: "top", JUNGLE: "jungle", MIDDLE: "mid", BOTTOM: "bot", UTILITY: "support" };

/** "Silver · mostly jungle", from the rank stored at the last sync. */
function rank(player: Player): string {
  const tier = !player.rank_checked
    ? "Rank not checked"
    : player.rank_tier
      ? player.rank_tier.charAt(0) + player.rank_tier.slice(1).toLowerCase()
      : "Unranked";
  return player.main_role ? `${tier} · mostly ${ROLES[player.main_role] ?? player.main_role}` : tier;
}

/** Who this report is about: Riot ID, rank, games covered, and the most played champions. */
export function ProfileHeader({ player, coverage }: { player: Player; coverage: Coverage }) {
  const p = coverage.player;
  const name = useChampionNames();
  return (
    <div className="flex flex-wrap items-center justify-between gap-6 border-b border-rule py-7">
      <div>
        <div className="display text-[30px] leading-none">
          {player.game_name}
          <span className="ml-1.5 font-sans text-[15px] font-normal tracking-normal text-ink3">#{player.tag_line}</span>
        </div>
        <div className="mt-2.5 text-[13px] text-ink2">
          {rank(player)} · {p.jungle_games} of {p.games} ranked games in the jungle · {shortDate(p.first_game)} to{" "}
          {shortDate(p.last_game)}
        </div>
      </div>
      <div className="flex items-center gap-6">
        {coverage.champions.slice(0, 3).map((c) => (
          <div key={c.champion} className="flex items-center gap-2.5">
            <ChampionIcon champion={c.champion} size={38} />
            <div className="leading-tight">
              <div className="text-[13px] text-ink">{name(c.champion)}</div>
              <div className="font-mono text-[11px] text-ink3">{c.games} games</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
