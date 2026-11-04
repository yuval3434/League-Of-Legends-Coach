// Words for the Matches page. It formats the API's numbers; it computes none.

export const QUEUES: Record<number, string> = {
  420: "Ranked Solo/Duo",
  440: "Ranked Flex",
};

export function queueName(id: number): string {
  return QUEUES[id] ?? `Queue ${id}`;
}

export const ROLES: Record<string, string> = {
  TOP: "Top",
  JUNGLE: "Jungle",
  MIDDLE: "Mid",
  BOTTOM: "Bot",
  UTILITY: "Support",
};

export function roleName(role: string): string {
  return ROLES[role] ?? (role || "—");
}

/** 1865 seconds as "31:05". */
export function gameLength(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function result(game: { win: boolean; is_remake: boolean }): "Win" | "Loss" | "Remake" {
  if (game.is_remake) return "Remake";
  return game.win ? "Win" : "Loss";
}

export function kda(p: { kills: number; deaths: number; assists: number }): string {
  return `${p.kills} / ${p.deaths} / ${p.assists}`;
}

/** "4 Nov 2026", in the viewer's time zone. */
export function gameDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
