// "Options for this draft": the coach's general notes on each available pool
// champion against this enemy team, from Riot's text. Paid, so the first click
// only counts the tokens (free) and shows the most it can cost; the second sends.

import { useEffect, useState } from "react";

import { api, type Board, type CoachAnswer, type CoachModel, type OptionsEstimate } from "../api";
import { estimateWords } from "../card";
import { Receipt } from "../pages/Coach";
import { CoachReply } from "./CoachReply";
import { ModelPicker } from "./ModelPicker";

// The button's default; the picker can change it for this page.
const DEFAULT_MODEL = "claude-sonnet-5-5";

export function DraftOptions({ board, player }: { board: Board; player: string | null }) {
  const [models, setModels] = useState<CoachModel[] | null>(null);
  const [modelId, setModelId] = useState(DEFAULT_MODEL);
  const [estimate, setEstimate] = useState<OptionsEstimate | null>(null);
  const [answer, setAnswer] = useState<CoachAnswer | null>(null);
  const [busy, setBusy] = useState<"counting" | "asking" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .coachModels()
      .then(setModels)
      .catch(() => setModels([]));
  }, []);

  // A new board or model needs a new count before anything is sent.
  const key = JSON.stringify([board, modelId, player]);
  useEffect(() => {
    setEstimate(null);
    setError(null);
  }, [key]);

  const chosen = models?.find((m) => m.id === modelId);
  const label = chosen?.label ?? modelId;

  function count() {
    setBusy("counting");
    setError(null);
    api
      .optionsEstimate(board, player, modelId)
      .then(setEstimate)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(null));
  }

  function ask() {
    setBusy("asking");
    setError(null);
    api
      .options(board, player, modelId)
      .then((reply) => {
        setAnswer(reply);
        setEstimate(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(null));
  }

  const words = estimate ? estimateWords(estimate, label) : null;
  return (
    <section className="mt-14">
      <div className="smallcaps text-ink3">Coach</div>
      <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Options for this draft</h2>
      <p className="mt-3 max-w-[720px] text-[15px] text-ink2">
        For each of your available champions, its general strengths and weaknesses against this enemy team, written
        from Riot's own text about the champions. It's general game knowledge, not your games: no ranking, no pick, and
        no claim about who wins.
      </p>

      {models && models.length > 0 && (
        <ModelPicker models={models} value={modelId} onChange={setModelId} disabled={busy !== null} costs={false} />
      )}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {!estimate ? (
          <button
            onClick={count}
            disabled={busy !== null || chosen?.available === false}
            className="rounded-[3px] border border-ink3 px-4 py-2 text-[14px] text-ink hover:bg-panel disabled:opacity-50"
          >
            {busy === "counting" ? "Counting…" : "See what it costs"}
          </button>
        ) : (
          <>
            <button
              onClick={ask}
              disabled={busy !== null}
              className="rounded-[3px] border border-ink3 bg-panel px-4 py-2 text-[14px] text-ink hover:border-ink disabled:opacity-50"
            >
              {busy === "asking" ? "Writing…" : `Ask, ${words!.main.charAt(0).toLowerCase()}${words!.main.slice(1)}`}
            </button>
            <button onClick={() => setEstimate(null)} disabled={busy !== null} className="text-[14px] text-ink3 hover:text-ink">
              Cancel
            </button>
          </>
        )}
      </div>
      {words && <p className="mt-2 max-w-[720px] font-mono text-[11px] leading-relaxed text-ink3">{words.detail}</p>}
      {error && <p className="mt-3 text-[14px] text-ink2">{error}</p>}

      {answer && (
        <article className="mt-8 max-w-[760px] border-t border-rule pt-5">
          <div className="text-[15px] leading-relaxed text-ink2">
            <CoachReply answer={answer} />
          </div>
          <Receipt answer={answer} />
        </article>
      )}
    </section>
  );
}
