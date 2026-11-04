// The player's games, newest first, and one game's two teams. Champions and
// stats only: no other player is named, even though match data has their names.

import { useEffect, useState } from "react";

import { api, type MatchDetail, type MatchPlayer, type MatchRow } from "../api";
import { ChampionIcon } from "../components/ChampionIcon";
import { Layout } from "../components/Layout";
import { useChampionNames } from "../ddragon";
import { gameDate, gameLength, kda, queueName, result, roleName } from "../matches";
import { fmt } from "../metrics";
import { usePlayer } from "../player";
import { href } from "../router";
import { subjectOf, Whose } from "../subject";

const TONE = { Win: "text-ink", Loss: "text-ink2", Remake: "text-ink3" } as const;

function Th({ children, right = false }: { children: string; right?: boolean }) {
  return (
    <th scope="col" className={`smallcaps border-b border-rule pb-2 pr-5 font-normal text-ink3 ${right ? "text-right" : "text-left"}`}>
      {children}
    </th>
  );
}

function GameList({ puuid }: { puuid: string | null }) {
  const name = useChampionNames();
  const [games, setGames] = useState<MatchRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    setGames(null);
    api
      .matches(puuid)
      .then((page) => {
        setGames(page.matches);
        setTotal(page.total);
      })
      .catch((e: Error) => setError(e.message));
  }, [puuid]);

  function more() {
    if (!games) return;
    setLoadingMore(true);
    api
      .matches(puuid, games.length)
      .then((page) => setGames([...games, ...page.matches]))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoadingMore(false));
  }

  if (error) return <p className="mt-8 text-ink2">{error}</p>;
  if (!games) return <p className="mt-8 font-mono text-[12px] text-ink3">Loading games…</p>;
  if (games.length === 0) return <p className="mt-8 text-ink2">No games synced yet.</p>;

  return (
    <>
      <div className="relative mt-8 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[14px]">
          <thead>
            <tr>
              <Th>Date</Th>
              <Th>Result</Th>
              <Th>Champion</Th>
              <Th>Role</Th>
              <Th right>K / D / A</Th>
              <Th right>CS</Th>
              <Th right>Length</Th>
              <Th>Queue</Th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const r = result(g);
              return (
                <tr key={g.match_id} className="border-b border-rule/60 hover:bg-panel/60">
                  <td className="py-2 pr-5 text-ink2">
                    <a href={href("matches", { id: g.match_id })} className="hover:text-ink">
                      {gameDate(g.game_start_at)}
                    </a>
                  </td>
                  <td className={`py-2 pr-5 ${TONE[r]}`}>{r}</td>
                  <td className="py-2 pr-5">
                    <a href={href("matches", { id: g.match_id })} className="flex items-center gap-2 text-ink hover:underline">
                      <ChampionIcon champion={g.champion} size={26} />
                      {name(g.champion)}
                    </a>
                  </td>
                  <td className="py-2 pr-5 text-ink2">{roleName(g.role)}</td>
                  <td className="py-2 pr-5 text-right font-mono">{kda(g)}</td>
                  <td className="py-2 pr-5 text-right font-mono">{g.cs}</td>
                  <td className="py-2 pr-5 text-right font-mono text-ink2">{gameLength(g.duration_s)}</td>
                  <td className="py-2 pr-5 text-ink3">{queueName(g.queue_id)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center gap-4 text-[13px] text-ink3">
        <span>
          {games.length} of {total} games
        </span>
        {games.length < total && (
          <button
            onClick={more}
            disabled={loadingMore}
            className="rounded-[3px] border border-rule px-3 py-1 text-ink2 hover:border-ink3/60 hover:text-ink disabled:opacity-50"
          >
            {loadingMore ? "Loading…" : "Show more"}
          </button>
        )}
      </div>
    </>
  );
}

function Team({ label, players, name }: { label: string; players: MatchPlayer[]; name: (id: string) => string }) {
  const won = players[0]?.win;
  return (
    <section className="mt-10">
      <h2 className="flex items-baseline gap-3">
        <span className="display text-[24px] leading-none">{label}</span>
        <span className="smallcaps text-ink3">{won ? "Won" : "Lost"}</span>
      </h2>
      <div className="relative mt-4 overflow-x-auto">
        <table className="w-full min-w-[680px] border-collapse text-[14px]">
          <thead>
            <tr>
              <Th>Role</Th>
              <Th>Champion</Th>
              <Th right>K / D / A</Th>
              <Th right>CS</Th>
              <Th right>Gold</Th>
              <Th right>Damage</Th>
              <Th right>Vision</Th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={`${p.side}-${p.role}-${p.champion}`} className={`border-b border-rule/60 ${p.is_me ? "bg-panel" : ""}`}>
                <td className="py-2 pl-1 pr-5 text-ink2">{roleName(p.role)}</td>
                <td className="py-2 pr-5">
                  <span className="flex items-center gap-2 text-ink">
                    <ChampionIcon champion={p.champion} size={26} />
                    {name(p.champion)}
                    {p.is_me && <span className="smallcaps text-ink3">You</span>}
                  </span>
                </td>
                <td className="py-2 pr-5 text-right font-mono">{kda(p)}</td>
                <td className="py-2 pr-5 text-right font-mono">
                  {p.cs}
                  <span className="ml-1.5 text-[11px] text-ink3">{fmt(p.cs_per_min, 1)}/min</span>
                </td>
                <td className="py-2 pr-5 text-right font-mono">{fmt(p.gold_earned, 0)}</td>
                <td className="py-2 pr-5 text-right font-mono">{fmt(p.damage_to_champions, 0)}</td>
                <td className="py-2 pr-5 text-right font-mono">{p.vision_score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MatchView({ id, puuid }: { id: string; puuid: string | null }) {
  const name = useChampionNames();
  const [game, setGame] = useState<MatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setGame(null);
    setError(null);
    api.match(id, puuid).then(setGame).catch((e: Error) => setError(e.message));
  }, [id, puuid]);

  const back = (
    <a href={href("matches")} className="text-[14px] text-ink3 hover:text-ink">
      ← All games
    </a>
  );
  if (error || !game) {
    return (
      <div className="pt-10">
        {back}
        <p className={`mt-8 ${error ? "text-ink2" : "font-mono text-[12px] text-ink3"}`}>{error ?? "Loading the game…"}</p>
      </div>
    );
  }

  const me = game.players.find((p) => p.is_me)!;
  const r = result({ win: me.win, is_remake: game.is_remake });
  return (
    <div className="pt-10">
      {back}
      <div className="mt-6 flex items-center gap-4">
        <ChampionIcon champion={me.champion} size={56} />
        <div>
          <div className="smallcaps text-ink3">
            {gameDate(game.game_start_at)} · {queueName(game.queue_id)} · {gameLength(game.duration_s)} · patch {game.patch}
          </div>
          <h1 className="display mt-1 text-[40px] leading-[1.05]">
            {r} on {name(me.champion)}, {roleName(me.role).toLowerCase()}
          </h1>
        </div>
      </div>
      {game.is_remake && (
        <p className="mt-4 max-w-[720px] text-[14px] text-ink2">
          This game was a remake, so no stat on the other pages counts it.
        </p>
      )}
      <Team label="Your team" players={game.players.filter((p) => p.side === "ally")} name={name} />
      <Team label="Enemy team" players={game.players.filter((p) => p.side === "enemy")} name={name} />
      <p className="mt-6 text-[13px] text-ink3">Champions only: no player is named.</p>
    </div>
  );
}

export function Matches({ id }: { id: string | null }) {
  const { puuid, player, error } = usePlayer();
  if (error || !player) {
    return (
      <Layout active="matches">
        <p className={`mt-16 ${error ? "text-ink2" : "font-mono text-[12px] text-ink3"}`}>{error ?? "Loading…"}</p>
      </Layout>
    );
  }
  return (
    <Layout active="matches">
      {id ? (
        <MatchView id={id} puuid={puuid} />
      ) : (
        <div className="pt-12">
          <div className="smallcaps text-ink3">Matches</div>
          <h1 className="display mt-1.5 text-[50px] leading-[1.02]">{Whose(subjectOf(player))} games</h1>
          <GameList puuid={puuid} />
        </div>
      )}
    </Layout>
  );
}
