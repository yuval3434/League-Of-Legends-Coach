import type { ReactNode } from "react";

import { HatchDefs } from "./Verdict";

const PAGES = [
  { id: "overview", label: "Overview" },
  { id: "champions", label: "Champions" },
  { id: "compare", label: "Compare" },
  { id: "coach", label: "Coach" },
];

export const RIOT_NOTICE =
  "LoL Coach isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties.";

export function Layout({ active, children }: { active: string; children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <HatchDefs />
      <div className="mx-auto max-w-[1200px] px-8 lg:px-12">
        <header className="flex items-baseline justify-between border-b border-rule py-5">
          <div className="flex items-baseline gap-3">
            <span className="display text-[22px] leading-none">LoL Coach</span>
            <span className="smallcaps text-ink3">Scouting report</span>
          </div>
          <nav className="flex gap-7 text-[14px]">
            {PAGES.map((page) => (
              <span
                key={page.id}
                aria-current={page.id === active ? "page" : undefined}
                className={
                  page.id === active
                    ? "border-b border-ink pb-1 text-ink"
                    : "pb-1 text-ink3"
                }
              >
                {page.label}
              </span>
            ))}
          </nav>
        </header>
        <main>{children}</main>
        <footer className="mt-24 border-t border-rule py-8 text-[12px] leading-relaxed text-ink3">
          <p className="max-w-[720px]">
            Every number here comes from SQL over real match data and is shown with its sample
            size. Margins are 95% confidence intervals.
          </p>
          <p className="mt-3 max-w-[720px]">{RIOT_NOTICE}</p>
        </footer>
      </div>
    </div>
  );
}
