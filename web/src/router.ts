// A tiny hash router: "#/champions", "#/coach?q=...". Four pages don't need a library.

import { useEffect, useState } from "react";

export type Page = "overview" | "champions" | "compare" | "coach";
export type Route = { page: Page; params: URLSearchParams };

const PAGES: Page[] = ["overview", "champions", "compare", "coach"];

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const page = PAGES.find((p) => p === path) ?? "overview";
  return { page, params: new URLSearchParams(query) };
}

export function href(page: Page, params?: Record<string, string>): string {
  const query = params ? `?${new URLSearchParams(params)}` : "";
  return `#/${page}${query}`;
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
