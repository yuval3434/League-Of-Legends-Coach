// Champion select: the board's limits, and words for the API's draft results.
// It shows options; it never picks one. Riot's League policy lists apps that
// dictate player decisions as unapproved, so nothing here ranks champions.

import type { Board, EnemyComposition, GapId, PoolEntry } from "./api";

// The board's three champion lists; its `role` isn't a side.
export type Side = "allies" | "enemies" | "bans";

export const SIDES: { side: Side; label: string; max: number }[] = [
  { side: "allies", label: "Your team", max: 4 },
  { side: "enemies", label: "Enemy team", max: 5 },
  { side: "bans", label: "Bans", max: 10 },
];

export const EMPTY: Board = { allies: [], enemies: [], bans: [] };

export const GAP_NAMES: Record<GapId, string> = {
  no_frontline: "No frontline",
  no_magic_damage: "No magic damage",
  no_physical_damage: "No physical damage",
};

/** Why a champion can't be added to a side, or null if it can. */
export function cantAdd(board: Board, side: Side, champion: string): string | null {
  const max = SIDES.find((s) => s.side === side)!.max;
  if (board[side].length >= max) return `${max} at most`;
  if ([board.allies, board.enemies, board.bans].some((list) => list.includes(champion))) return "Already on the board";
  return null;
}

export function add(board: Board, side: Side, champion: string): Board {
  return cantAdd(board, side, champion) ? board : { ...board, [side]: [...board[side], champion] };
}

export function remove(board: Board, side: Side, champion: string): Board {
  return { ...board, [side]: board[side].filter((c) => c !== champion) };
}

/** The win rate in words: "Too early to tell" under 10 games, never a bare percentage. */
export function winRateCell(entry: PoolEntry): { main: string; detail: string } {
  const record = `won ${entry.wins} of ${entry.games}`;
  if (entry.low_sample || entry.margin_win_rate_pct == null || entry.margin_win_rate_pct === 0) {
    return { main: "Too early to tell", detail: record };
  }
  return { main: `${entry.win_rate_pct}%`, detail: `give or take ${entry.margin_win_rate_pct} · ${record}` };
}

function list(names: string[]): string {
  return names.length <= 1 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** The board as a question for the coach, which asks to be shown, not told. */
export function coachQuestion(board: Board, name: (id: string) => string): string {
  const parts = [
    board.allies.length ? `my team has ${list(board.allies.map(name))}` : "my team hasn't picked yet",
    board.enemies.length ? `the enemy has ${list(board.enemies.map(name))}` : null,
    board.bans.length ? `${list(board.bans.map(name))} ${board.bans.length === 1 ? "is" : "are"} banned` : null,
  ].filter(Boolean);
  return `Champion select: ${parts.join(", ")}. What does my team lack, and which of my champions fill it?`;
}

const COUNT = ["no", "one", "two", "three", "four", "five"];

function plural(n: number, word: string): string {
  return `${COUNT[n] ?? n} ${word}${n === 1 ? "" : "s"}`;
}

/** "Mostly physical: 4 of 4". The label is the API's; this only words it. */
export function damageWords(c: EnemyComposition): { main: string; detail: string } {
  const { physical, magic, mixed } = c.damage;
  const parts = [
    physical ? `${physical} physical` : null,
    magic ? `${magic} magic` : null,
    mixed ? `${mixed} both` : null,
  ].filter(Boolean);
  const detail = `${parts.join(", ")}, of ${c.picked} picked`;
  if (c.mix === "mostly_physical") return { main: `Mostly physical: ${physical} of ${c.picked}`, detail };
  if (c.mix === "mostly_magic") return { main: `Mostly magic: ${magic} of ${c.picked}`, detail };
  if (c.mix === "mixed") return { main: "Mixed", detail };
  return { main: "Too few picks to say", detail: `${detail}; the mix is called from 3 picks` };
}

/** "One tank: Malphite", or what stands in for a frontline. */
export function frontlineWords(c: EnemyComposition, name: (id: string) => string): string {
  const names = (ids: string[]) => ids.map(name).join(", ");
  const tanks = c.tanks.length ? `${plural(c.tanks.length, "tank")}: ${names(c.tanks)}` : null;
  const fighters = c.fighters.length ? `${plural(c.fighters.length, "fighter")}: ${names(c.fighters)}` : null;
  const said = [tanks, fighters].filter(Boolean).join("; ");
  if (!c.has_frontline) return said ? `No frontline. ${capital(said)}` : "No frontline: no tank or fighter";
  return capital(tanks ? said : `No tank, but ${said}`);
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
