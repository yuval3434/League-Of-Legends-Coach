// Add a player by Riot ID, watch the sync, and see everyone already synced.
// Syncing is free but uses the Riot call budget, so only one runs at a time.

import { useEffect, useState } from "react";

import { api, type PlayerRow, type SyncStatus } from "../api";
import { Layout } from "../components/Layout";
import { PLAYERS_CHANGED } from "../components/PlayerSwitcher";
import { href } from "../router";
import { parseRiotId, progressOf, timeLeft } from "../sync";

const ROLES: Record<string, string> = { TOP: "Top", JUNGLE: "Jungle", MIDDLE: "Mid", BOTTOM: "Bot", UTILITY: "Support" };

function tier(row: PlayerRow): string {
  if (!row.rank_checked_at) return "Rank not checked";
  return row.rank_tier ? row.rank_tier.charAt(0) + row.rank_tier.slice(1).toLowerCase() : "Unranked";
}

function benchmarks(row: PlayerRow): string {
  const fits = Object.entries(row.benchmarks)
    .filter(([, reason]) => reason === null)
    .map(([cohort]) => cohort.charAt(0).toUpperCase() + cohort.slice(1));
  return fits.length ? fits.join(", ") : "No benchmark";
}

function ProgressBar({ status }: { status: SyncStatus }) {
  const p = progressOf(status);
  return (
    <div className="mt-6 max-w-[620px]" aria-live="polite">
      <div className="flex items-baseline justify-between text-[14px]">
        <span className="text-ink">Syncing {status.riot_id}</span>
        <span className="font-mono text-[12px] text-ink3">{timeLeft(p.secondsLeft)}</span>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(p.fraction * 100)}
        aria-label={`Syncing ${status.riot_id}`}
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-rule"
      >
        <div className="h-full rounded-full bg-ink transition-[width] duration-500" style={{ width: `${p.fraction * 100}%` }} />
      </div>
      <div className="mt-2 text-[13px] text-ink3">{p.label}</div>
    </div>
  );
}

function Result({ status }: { status: SyncStatus }) {
  if (status.state === "failed") {
    return (
      <p className="mt-6 max-w-[620px] border-l-2 border-accent pl-4 text-[15px] text-ink2">
        {status.riot_id && <span className="text-ink">{status.riot_id}: </span>}
        {status.error}
      </p>
    );
  }
  if (status.state !== "done" || !status.puuid) return null;
  return (
    <p className="mt-6 max-w-[620px] text-[15px] text-ink2">
      Synced {status.riot_id}: {status.matches_parsed} new matches
      {status.matches_failed ? `, ${status.matches_failed} that failed and will be retried next time` : ""}.{" "}
      <a
        href={href("overview", { player: status.puuid })}
        className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink3"
      >
        See their overview
      </a>
    </p>
  );
}

export function Players() {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [players, setPlayers] = useState<PlayerRow[] | null>(null);
  const running = status?.state === "running";

  const loadPlayers = () => api.players().then(setPlayers).catch(() => setPlayers([]));

  useEffect(() => {
    loadPlayers();
    // A sync started earlier, or from elsewhere, still shows its progress.
    api.syncStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  // While a sync runs, ask the server how far it is every second and a half.
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      api.syncStatus().then((next) => {
        setStatus(next);
        if (next.state !== "running") {
          loadPlayers();
          window.dispatchEvent(new Event(PLAYERS_CHANGED));
        }
      });
    }, 1500);
    return () => clearInterval(timer);
  }, [running]);

  async function start(name: string, tag: string) {
    setProblem(null);
    try {
      setStatus(await api.sync(name, tag));
    } catch (e) {
      setProblem((e as Error).message);
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const id = parseRiotId(text);
    if ("error" in id) return setProblem(id.error);
    start(id.name, id.tag);
  }

  return (
    <Layout active="players">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Players</div>
        <h1 className="display mt-1.5 max-w-[920px] text-[50px] leading-[1.02]">Add a player</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          Enter a Riot ID to sync their last 100 ranked games. It takes about 4 minutes, because Riot's development key
          allows 100 calls every 2 minutes and each match needs 2. Their games stay in this computer's database, like
          yours. They get the same verdicts as you, and a benchmark only where their rank and role have one.
        </p>
      </div>

      <form onSubmit={submit} className="mt-10 flex max-w-[620px] flex-wrap items-start gap-3">
        <div className="min-w-[260px] flex-1">
          <label htmlFor="riot-id" className="smallcaps text-ink3">
            Riot ID
          </label>
          <input
            id="riot-id"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Name#TAG"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? "riot-id-problem" : undefined}
            className="mt-2 w-full rounded-[3px] border border-rule bg-panel px-4 py-2.5 text-[16px] text-ink placeholder:text-faint focus:border-ink3 focus:outline-none"
          />
          {problem && (
            <p id="riot-id-problem" className="mt-2 text-[14px] text-accent">
              {problem}
            </p>
          )}
        </div>
        <button
          type="submit"
          disabled={running}
          className="mt-[30px] rounded-[3px] bg-ink px-5 py-2.5 text-[14px] font-medium text-page hover:bg-ink2 disabled:cursor-not-allowed disabled:bg-rule disabled:text-ink3"
        >
          {running ? "Syncing…" : "Sync"}
        </button>
      </form>

      {status && running && <ProgressBar status={status} />}
      {status && !running && <Result status={status} />}

      <section className="mt-16">
        <div className="smallcaps text-ink3">Synced players</div>
        {players === null ? (
          <p className="mt-4 font-mono text-[12px] text-ink3">Loading…</p>
        ) : (
          <table className="mt-4 w-full max-w-[900px] border-collapse text-[14px]">
            <thead>
              <tr>
                {["Player", "Rank", "Main role", "Games", "Benchmarks", ""].map((h) => (
                  <th key={h} scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {players.map((p) => (
                <tr key={p.puuid} className="border-b border-rule/60">
                  <th scope="row" className="py-3 pr-4 text-left font-normal text-ink">
                    <a
                      href={href("overview", { player: p.is_owner ? "" : p.puuid })}
                      className="underline decoration-rule underline-offset-4 hover:decoration-ink3"
                    >
                      {p.game_name}
                    </a>
                    <span className="text-ink3">#{p.tag_line}</span>
                    {p.is_owner && <span className="ml-2 smallcaps text-ink3">you</span>}
                  </th>
                  <td className="py-3 pr-4 text-ink2">{tier(p)}</td>
                  <td className="py-3 pr-4 text-ink2">{p.main_role ? ROLES[p.main_role] ?? p.main_role : "—"}</td>
                  <td className="py-3 pr-4 text-ink2">{p.games}</td>
                  <td className="py-3 pr-4 text-ink2">{benchmarks(p)}</td>
                  <td className="py-3 text-right">
                    <button
                      onClick={() => start(p.game_name, p.tag_line)}
                      disabled={running}
                      className="text-[13px] text-ink3 underline decoration-rule underline-offset-4 hover:text-ink disabled:no-underline disabled:opacity-50"
                    >
                      Sync again
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-4 max-w-[720px] text-[13px] text-ink3">
          Ranks are current solo/duo ranks from the last sync: Riot's match data doesn't say what rank each game was
          played at.
        </p>
      </section>
    </Layout>
  );
}
