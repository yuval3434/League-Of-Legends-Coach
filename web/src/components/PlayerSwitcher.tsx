// The header's player switcher: every synced player, the owner first, plus a
// way to add one. Picking a player keeps the current page.

import { useEffect, useRef, useState } from "react";

import { api, type PlayerRow } from "../api";
import { href, type Page, selectedPlayer } from "../router";

/** Fired after a sync finishes, so the switcher lists the new player. */
export const PLAYERS_CHANGED = "lolcoach:players-changed";

function tier(row: PlayerRow): string {
  if (!row.rank_checked_at) return "Rank not checked";
  return row.rank_tier ? row.rank_tier.charAt(0) + row.rank_tier.slice(1).toLowerCase() : "Unranked";
}

export function PlayerSwitcher({ page }: { page: Page }) {
  const [players, setPlayers] = useState<PlayerRow[]>([]);
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  const current = selectedPlayer();

  useEffect(() => {
    const load = () => api.players().then(setPlayers).catch(() => setPlayers([]));
    load();
    window.addEventListener(PLAYERS_CHANGED, load);
    return () => window.removeEventListener(PLAYERS_CHANGED, load);
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !menu.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const selected = players.find((p) => (current ? p.puuid === current : p.is_owner));
  // The Players page isn't about one player, so picking one there opens their Overview.
  const target: Page = page === "players" ? "overview" : page;

  return (
    <div ref={menu} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-2 rounded-[3px] border border-rule px-3 py-1.5 text-[13px] text-ink hover:border-ink3"
      >
        <span className="max-w-[160px] truncate">{selected ? selected.game_name : "Players"}</span>
        {selected && !selected.is_owner && <span className="text-ink3">viewing</span>}
        <svg width={9} height={6} viewBox="0 0 9 6" aria-hidden>
          <path d="M1 1l3.5 3.5L8 1" fill="none" stroke="currentColor" strokeWidth={1.3} />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-2 w-[300px] rounded-[3px] border border-rule bg-panel py-1.5 shadow-lg shadow-black/40"
        >
          {players.map((p) => (
            <a
              key={p.puuid}
              role="menuitem"
              href={href(target, { player: p.is_owner ? "" : p.puuid })}
              onClick={() => setOpen(false)}
              aria-current={p === selected ? "true" : undefined}
              className={`flex items-baseline justify-between gap-3 px-3.5 py-2 text-[14px] hover:bg-page ${
                p === selected ? "text-ink" : "text-ink2"
              }`}
            >
              <span className="truncate">
                {p.game_name}
                <span className="text-ink3">#{p.tag_line}</span>
                {p.is_owner && <span className="ml-1.5 smallcaps text-ink3">you</span>}
              </span>
              <span className="shrink-0 font-mono text-[11px] text-ink3">
                {tier(p)} · {p.games} games
              </span>
            </a>
          ))}
          <div className="my-1.5 border-t border-rule" />
          <a
            role="menuitem"
            href={href("players")}
            onClick={() => setOpen(false)}
            className="block px-3.5 py-2 text-[14px] text-ink2 hover:bg-page hover:text-ink"
          >
            Add a player…
          </a>
        </div>
      )}
    </div>
  );
}
