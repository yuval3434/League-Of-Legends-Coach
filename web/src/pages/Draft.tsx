// Champion select. The player types in the champions on screen; nothing is read
// from the game client, and no player is named. The page shows what the team
// lacks and which of the player's own champions fill it. It never picks one,
// and it has no matchup data.

import { useEffect, useId, useState } from "react";

import { api, type Board, type DraftBoard, type DraftChampion } from "../api";
import { ChampionIcon } from "../components/ChampionIcon";
import { Layout } from "../components/Layout";
import { add, cantAdd, coachQuestion, EMPTY, GAP_NAMES, remove, SIDES, type Side, winRateCell } from "../draft";
import { usePlayer } from "../player";
import { askCoach } from "../router";
import { subjectOf } from "../subject";

function Picker({
  side,
  label,
  max,
  board,
  champions,
  onChange,
}: {
  side: Side;
  label: string;
  max: number;
  board: Board;
  champions: DraftChampion[];
  onChange: (board: Board) => void;
}) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const listId = useId();
  const name = (id: string) => champions.find((c) => c.champion === id)?.name ?? id;

  function tryAdd(value: string) {
    const found = champions.find((c) => c.name.toLowerCase() === value.trim().toLowerCase());
    if (!found) return false;
    const why = cantAdd(board, side, found.champion);
    setProblem(why);
    if (!why) {
      onChange(add(board, side, found.champion));
      setText("");
    }
    return true;
  }

  return (
    <div className="border-t border-rule pt-3">
      <div className="flex items-baseline justify-between">
        <h3 className="smallcaps text-ink3">{label}</h3>
        <span className="font-mono text-[11px] text-ink3">
          {board[side].length} of {max}
        </span>
      </div>
      <ul className="mt-2 flex min-h-[36px] flex-wrap gap-1.5">
        {board[side].map((id) => (
          <li key={id} className="flex items-center gap-1.5 rounded-[3px] border border-rule py-0.5 pl-0.5 pr-1.5 text-[13px]">
            <ChampionIcon champion={id} size={24} />
            {name(id)}
            <button
              aria-label={`Remove ${name(id)}`}
              onClick={() => onChange(remove(board, side, id))}
              className="ml-0.5 text-ink3 hover:text-ink"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      {board[side].length < max && (
        <input
          list={listId}
          value={text}
          aria-label={`Add a champion to ${label.toLowerCase()}`}
          placeholder="Type a champion"
          onChange={(e) => {
            setText(e.target.value);
            setProblem(null);
            // Choosing from the list fills in the whole name, so add it straight away.
            tryAdd(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !tryAdd(text)) setProblem("No champion by that name");
          }}
          className="mt-2 w-full rounded-[3px] border border-rule bg-transparent px-2.5 py-1.5 text-[14px] text-ink placeholder:text-ink3 focus:border-ink3 focus:outline-none"
        />
      )}
      <datalist id={listId}>
        {champions.map((c) => (
          <option key={c.champion} value={c.name} />
        ))}
      </datalist>
      {problem && <p className="mt-1 text-[12px] text-ink2">{problem}</p>}
    </div>
  );
}

function Results({ result, name }: { result: DraftBoard; name: (id: string) => string }) {
  const noTeam = result.your_team.length === 0;
  return (
    <>
      <section className="mt-14">
        <div className="smallcaps text-ink3">Your team</div>
        <h2 className="display mt-1.5 text-[30px] leading-[1.1]">What it lacks</h2>
        {noTeam ? (
          <p className="mt-4 text-[15px] text-ink2">Add your teammates' champions to check what the team lacks.</p>
        ) : result.gaps.length === 0 ? (
          <p className="mt-4 text-[15px] text-ink2">Nothing, by these rules.</p>
        ) : (
          <ul className="mt-5 space-y-5">
            {result.gaps.map((gap) => (
              <li key={gap.gap} className="border-t border-rule pt-3">
                <div className="text-[16px] text-ink">{GAP_NAMES[gap.gap]}</div>
                {/* The description repeats the gap's name before a colon; show only the rule. */}
                <p className="mt-1 text-[13px] text-ink3">{gap.description.replace(/^[^:]*:\s*(\w)/, (_, first: string) => first.toUpperCase())}</p>
                <p className="mt-2 text-[14px] text-ink2">
                  {gap.filled_by.length
                    ? `Your champions that add it: ${gap.filled_by.map(name).join(", ")}.`
                    : "None of your champions with 3 or more games adds it."}
                </p>
              </li>
            ))}
          </ul>
        )}
        <details className="mt-4 text-[13px] text-ink3">
          <summary className="cursor-pointer hover:text-ink2">The rules</summary>
          <ul className="mt-2 space-y-1">
            {result.rules_checked.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
          <p className="mt-2">
            Tags and damage types come from Riot's Data Dragon ({result.data_dragon_version}): fixed ratings, not
            stats from games.
          </p>
        </details>
      </section>

      <section className="mt-14">
        <div className="smallcaps text-ink3">Your pool</div>
        <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Your jungle champions</h2>
        {result.pool.length === 0 ? (
          <p className="mt-4 text-[15px] text-ink2">No champion has 3 or more jungle games yet.</p>
        ) : (
          <div className="relative mt-5 overflow-x-auto">
            <table className="w-full min-w-[600px] border-collapse text-[14px]">
              <thead>
                <tr>
                  {["Champion", "Games", "Win rate", "Type", "Adds"].map((h) => (
                    <th key={h} scope="col" className="smallcaps border-b border-rule pb-2 pr-6 text-left font-normal text-ink3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.pool.map((p) => {
                  const rate = winRateCell(p);
                  return (
                    <tr key={p.champion} className={`border-b border-rule/60 align-top ${p.unavailable ? "text-ink3" : ""}`}>
                      <th scope="row" className="py-2.5 pr-6 text-left font-normal">
                        <span className="flex items-center gap-2">
                          <ChampionIcon champion={p.champion} size={28} />
                          {name(p.champion)}
                        </span>
                      </th>
                      <td className="py-2.5 pr-6 font-mono">{p.games}</td>
                      <td className="py-2.5 pr-6">
                        <div>{rate.main}</div>
                        <div className="font-mono text-[11px] text-ink3">{rate.detail}</div>
                      </td>
                      <td className="py-2.5 pr-6 text-ink2">
                        {p.tags?.join(", ") ?? "—"}
                        {p.damage && <div className="text-[12px] text-ink3">{p.damage} damage</div>}
                      </td>
                      <td className="py-2.5 pr-6">
                        {p.unavailable
                          ? p.unavailable === "banned"
                            ? "Banned"
                            : "Picked"
                          : p.fills?.length
                            ? p.fills.map((g) => GAP_NAMES[g].replace(/^No /, "")).join(", ")
                            : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-[13px] text-ink3">Most played first. This isn't a ranking: the pick is yours.</p>
      </section>

      {result.enemy_team.length > 0 && (
        <section className="mt-14">
          <div className="smallcaps text-ink3">Enemy team</div>
          <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Matchups</h2>
          <ul className="mt-5 space-y-2">
            {result.enemy_team.map((e) => (
              <li key={e.champion} className="flex items-center gap-3 text-[14px]">
                <ChampionIcon champion={e.champion} size={28} />
                <span className="text-ink">{e.name}</span>
                <span className="text-ink3">No matchup data</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 max-w-[720px] text-[13px] text-ink3">{result.matchups}</p>
        </section>
      )}
    </>
  );
}

export function Draft() {
  const { puuid, player, error: playerError } = usePlayer();
  const [champions, setChampions] = useState<DraftChampion[] | null>(null);
  const [board, setBoard] = useState<Board>(EMPTY);
  const [result, setResult] = useState<DraftBoard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .draftChampions()
      .then((r) => setChampions(r.champions))
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    let current = true;
    api
      .draft(board, puuid)
      .then((r) => current && (setResult(r), setError(null)))
      .catch((e: Error) => current && setError(e.message));
    return () => {
      current = false;
    };
  }, [board, puuid]);

  const failed = playerError ?? (champions === null ? error : null);
  if (failed || !player || !champions) {
    return (
      <Layout active="draft">
        <p className={`mt-16 ${failed ? "text-ink2" : "font-mono text-[12px] text-ink3"}`}>
          {failed ?? "Loading champions…"}
        </p>
      </Layout>
    );
  }

  const s = subjectOf(player);
  const name = (id: string) => champions.find((c) => c.champion === id)?.name ?? id;
  return (
    <Layout active="draft">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Champion select</div>
        <h1 className="display mt-1.5 text-[50px] leading-[1.02]">What the team lacks</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          Add the champions you see on screen. Nothing is read from the game client and no player is named: only
          champions. The page shows what {s.you ? "your" : "the"} team lacks and which of{" "}
          {s.you ? "your" : `${s.name}'s`} jungle champions add it. It doesn't choose for {s.you ? "you" : s.name}.
        </p>
      </div>

      <div className="mt-10 grid gap-x-10 gap-y-6 md:grid-cols-3">
        {SIDES.map(({ side, label, max }) => (
          <Picker key={side} side={side} label={label} max={max} board={board} champions={champions} onChange={setBoard} />
        ))}
      </div>
      {error && <p className="mt-4 text-[14px] text-ink2">{error}</p>}

      {result && <Results result={result} name={name} />}

      <div className="mt-10">
        <a
          href={askCoach(coachQuestion(board, name))}
          className="text-[14px] text-ink2 underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink3"
        >
          Ask the coach about this board
        </a>
      </div>
    </Layout>
  );
}
