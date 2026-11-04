// A tiny hash router: "#/champions?player=...", "#/coach?q=...". A handful of
// pages don't need a library. The selected player rides along in every link.

import { useEffect, useState } from "react";

export type Page = "overview" | "champions" | "compare" | "draft" | "coach" | "players" | "settings";
export type Route = { page: Page; params: URLSearchParams };

const PAGES: Page[] = ["overview", "champions", "compare", "draft", "coach", "players", "settings"];

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const page = PAGES.find((p) => p === path) ?? "overview";
  return { page, params: new URLSearchParams(query) };
}

/** The selected player's PUUID, or null for the owner. */
export function selectedPlayer(hash = window.location.hash): string | null {
  return parseRoute(hash).params.get("player");
}

/**
 * A link to a page. It keeps the selected player unless `params.player` says
 * otherwise; an empty string there means the owner.
 */
export function href(page: Page, params: Record<string, string> = {}, hash?: string): string {
  const player = "player" in params ? params.player : selectedPlayer(hash ?? (typeof window === "undefined" ? "" : window.location.hash));
  const kept = Object.entries({ ...params, player: player ?? "" }).filter(([, v]) => v !== "");
  return `#/${page}${kept.length ? `?${new URLSearchParams(kept)}` : ""}`;
}

/** A link to the Coach page with the question already typed in. */
export function askCoach(question: string): string {
  return href("coach", { q: question });
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const update = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}
