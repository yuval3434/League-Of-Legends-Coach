// Ask the coach. Each reply carries a receipt worked out by the server: the
// tools it called and how many games they rested on, whether its numbers
// checked out, and what the answer cost. Asking is a paid call, so nothing
// here sends a question without the player pressing the button.

import { useEffect, useRef, useState, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type CoachAnswer, type CoachModel } from "../api";
import { CHECK, costWords, restsOnFewGames, sampleWords, toolLabel } from "../coach";
import { Layout } from "../components/Layout";
import { ModelPicker } from "../components/ModelPicker";
import { Marker } from "../components/Verdict";
import { useChampionNames } from "../ddragon";
import { costWords as estimateWords, MODEL_STORE, pickModel } from "../models";
import { usePlayer } from "../player";
import { href } from "../router";
import { type Subject, subjectOf, YOU, whose } from "../subject";

type Exchange = {
  question: string;
  // The Riot ID the question was about, when it wasn't the owner.
  about?: string;
  answer?: CoachAnswer;
  error?: string;
  seconds?: number;
};

const STORE = "lolcoach.coach.thread";

/** Starter questions, about you or about the selected player. */
function starters(s: Subject): string[] {
  if (s.you) {
    return [
      "What's the one thing I should work on first?",
      "How does my farming compare with Silver junglers?",
      "Do I die more than I should before objectives?",
    ];
  }
  return [
    `What's the one thing ${s.name} should work on first?`,
    `Which champions does ${s.name} play best?`,
    `Does ${s.name} die more than they should before objectives?`,
  ];
}

const MODELS: Record<string, string> = {
  "claude-opus-5-5": "Opus 5.5",
  "claude-sonnet-5-5": "Sonnet 5.5",
  "claude-haiku-5-5": "Haiku 5.5",
};

// Answers cost money, so a reload shouldn't lose them. Storage can be blocked;
// then the thread just lives for this visit.
function loadThread(): Exchange[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE) ?? "[]") as Exchange[];
    return saved.filter((e) => e.answer || e.error);
  } catch {
    return [];
  }
}

function saveThread(thread: Exchange[]) {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(thread.filter((e) => e.answer || e.error)));
  } catch {
    /* storage blocked: keep the thread in memory only */
  }
}

/** The coach writes Markdown; these give it the page's type and rules. Raw HTML isn't rendered. */
export const MARKDOWN: Components = {
  p: ({ children }) => <p className="mt-3 first:mt-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  ul: ({ children }) => <ul className="mt-3 list-disc space-y-1.5 pl-5 marker:text-ink3">{children}</ul>,
  ol: ({ children }) => <ol className="mt-3 list-decimal space-y-1.5 pl-5 marker:text-ink3">{children}</ol>,
  h1: ({ children }) => <h3 className="mt-5 text-[17px] font-semibold text-ink">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-5 text-[17px] font-semibold text-ink">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-4 text-[16px] font-semibold text-ink">{children}</h4>,
  table: ({ children }) => (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full border-collapse text-[14px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="smallcaps border-b border-rule px-3 pb-2 text-left font-normal text-ink3 first:pl-0">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-rule/60 px-3 py-2 first:pl-0">{children}</td>,
  code: ({ children }) => <code className="font-mono text-[13px] text-ink">{children}</code>,
  a: ({ children }) => <span className="text-ink">{children}</span>,
};

/** The number check's own mark, so it isn't read as a verdict marker. */
function CheckMark({ tone }: { tone: "ok" | "warn" | "plain" }) {
  if (tone === "warn") return <Marker state="behind" size={8} />;
  if (tone === "plain") return <Marker state="unclear" size={8} />;
  return (
    <svg width={11} height={9} viewBox="0 0 11 9" aria-hidden className="shrink-0">
      <path d="M1 4.5 4 7.5 10 1" fill="none" stroke="var(--color-ink)" strokeWidth={1.6} />
    </svg>
  );
}

function ReceiptRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-x-6 gap-y-1 border-t border-rule py-3 md:grid-cols-[120px_1fr]">
      <div className="smallcaps pt-0.5 text-ink3">{label}</div>
      <div className="text-[13px] text-ink2">{children}</div>
    </div>
  );
}

export function Receipt({ answer, seconds }: { answer: CoachAnswer; seconds?: number }) {
  const name = useChampionNames();
  const check = CHECK[answer.status];
  const models = [...new Set(answer.models)].map((m) => MODELS[m] ?? m).join(" and ");
  return (
    <div className="mt-6 max-w-[760px]">
      <ReceiptRow label="Number check">
        <span className={`inline-flex items-start gap-2 ${check.tone === "warn" ? "text-accent" : check.tone === "ok" ? "text-ink2" : "text-ink3"}`}>
          <span className="pt-[5px]">
            <CheckMark tone={check.tone} />
          </span>
          <span>
            {check.words}
            {answer.status === "unverified" && (
              <span className="ml-1 font-mono text-[12px]">{answer.caught_numbers.join(", ")}</span>
            )}
          </span>
        </span>
      </ReceiptRow>
      <ReceiptRow label="Looked at">
        {answer.tools.length === 0 ? (
          <span className="text-ink3">No stats: this answer didn't look anything up.</span>
        ) : (
          <ul className="space-y-1">
            {answer.tools.map((tool, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-2">
                {restsOnFewGames(tool) && <Marker state="low" size={8} />}
                <span className="text-ink">{toolLabel(tool, name)}</span>
                <span className="text-ink3">· {sampleWords(tool)}</span>
              </li>
            ))}
          </ul>
        )}
      </ReceiptRow>
      <ReceiptRow label="Cost">
        <span className="text-ink">{costWords(answer)}</span>
        {models && <span className="text-ink3"> · answered by {models}</span>}
        {seconds ? <span className="text-ink3"> · {seconds} s</span> : null}
      </ReceiptRow>
    </div>
  );
}

function ExchangeView({ exchange }: { exchange: Exchange }) {
  return (
    <article className="border-t border-ink/30 pt-6">
      <div className="smallcaps text-ink3">You asked{exchange.about && `, about ${exchange.about}`}</div>
      <p className="mt-1.5 text-[17px] text-ink">{exchange.question}</p>
      {exchange.error && <p className="mt-5 text-[15px] text-ink2">{exchange.error}</p>}
      {exchange.answer && (
        <>
          <div className="mt-6 max-w-[760px] text-[15px] leading-relaxed text-ink2">
            <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN}>
              {exchange.answer.text}
            </Markdown>
          </div>
          <Receipt answer={exchange.answer} seconds={exchange.seconds} />
        </>
      )}
    </article>
  );
}

function Waiting({ question }: { question: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <article className="border-t border-ink/30 pt-6" aria-live="polite">
      <div className="smallcaps text-ink3">You asked</div>
      <p className="mt-1.5 text-[17px] text-ink">{question}</p>
      <p className="mt-5 font-mono text-[12px] text-ink3">
        The coach is looking up your stats and checking its numbers… {seconds} s
      </p>
    </article>
  );
}

function remembered(): string | null {
  try {
    return localStorage.getItem(MODEL_STORE);
  } catch {
    return null;
  }
}

function remember(id: string) {
  try {
    localStorage.setItem(MODEL_STORE, id);
  } catch {
    /* storage blocked: the choice lasts for this visit */
  }
}

export function Coach({ question: carried }: { question: string }) {
  const [models, setModels] = useState<CoachModel[] | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [draft, setDraft] = useState(carried);
  const [thread, setThread] = useState<Exchange[]>(loadThread);
  const [pending, setPending] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const { puuid, player } = usePlayer();
  const s = player ? subjectOf(player) : YOU;
  const about = player && !player.is_owner ? `${player.game_name}#${player.tag_line}` : undefined;

  useEffect(() => {
    api
      .coachModels()
      .then((list) => {
        setModels(list);
        setModelId(pickModel(list, remembered()));
      })
      .catch(() => setModels([]));
  }, []);

  const chosen = models?.find((m) => m.id === modelId) ?? null;
  const available = models === null ? null : Boolean(chosen?.available);
  const anyReady = models?.some((m) => m.available) ?? true;

  function choose(id: string) {
    setModelId(id);
    remember(id);
  }

  // A question carried from another page fills the box; it's never sent for you.
  useEffect(() => {
    if (carried) {
      setDraft(carried);
      box.current?.focus();
    }
  }, [carried]);

  useEffect(() => saveThread(thread), [thread]);

  async function ask() {
    const question = draft.trim();
    if (!question || pending || !available || !player) return;
    setPending(question);
    setDraft("");
    const started = performance.now();
    try {
      // The server picks the player from this PUUID; the model never sees one.
      const answer = await api.ask(question, puuid, modelId);
      const seconds = Math.round((performance.now() - started) / 1000);
      setThread((t) => [...t, { question, about, answer, seconds }]);
    } catch (e) {
      setThread((t) => [...t, { question, about, error: (e as Error).message }]);
    } finally {
      setPending(null);
    }
  }

  const canAsk = available === true && player !== null && pending === null && draft.trim().length > 0;

  return (
    <Layout active="coach">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Coach</div>
        <h1 className="display mt-1.5 max-w-[920px] text-[50px] leading-[1.02]">Ask about {whose(s)} games</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          The coach looks up {whose(s)} stats with the same tools as these pages and explains them. It doesn't make up
          numbers: every reply is checked against the data it looked at, and the receipt under it says what that was.
          Each question is answered on its own, without the earlier ones.
        </p>
      </div>

      {!anyReady && (
        <div className="mt-8 max-w-[720px] border-l-2 border-accent pl-4 text-[15px] text-ink2">
          <p className="text-ink">No model can answer right now.</p>
          <p className="mt-1">
            Claude models need an Anthropic API key, which you can add in{" "}
            <a href={href("settings")} className="text-ink underline decoration-rule underline-offset-4">
              Settings
            </a>
            . The local model needs Ollama running on this computer. The other pages work without either.
          </p>
        </div>
      )}

      <div className="mt-12 space-y-12">
        {thread.map((exchange, i) => (
          <ExchangeView key={i} exchange={exchange} />
        ))}
        {pending && <Waiting question={pending} />}
      </div>

      <section className={`${thread.length || pending ? "mt-12" : "mt-10"} max-w-[760px] border-t border-rule pt-6`}>
        <label htmlFor="question" className="smallcaps text-ink3">
          Your question{about && <span className="normal-case tracking-normal">: asking about {about}</span>}
        </label>
        <textarea
          id="question"
          ref={box}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              ask();
            }
          }}
          rows={3}
          maxLength={2000}
          placeholder="How am I doing on Viego?"
          className="mt-2 w-full resize-y rounded-[3px] border border-rule bg-panel px-4 py-3 text-[16px] text-ink placeholder:text-faint focus:border-ink3 focus:outline-none"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <p className="text-[13px] text-ink3">
            {chosen?.estimated_cost_usd === 0
              ? "Runs on this computer: free, but several minutes per answer and less reliable. Ctrl+Enter sends."
              : chosen
                ? `A paid call, ${estimateWords(chosen)}. Ctrl+Enter sends.`
                : "Ctrl+Enter sends."}
          </p>
          <button
            onClick={ask}
            disabled={!canAsk}
            className="rounded-[3px] bg-ink px-5 py-2 text-[14px] font-medium text-page hover:bg-ink2 disabled:cursor-not-allowed disabled:bg-rule disabled:text-ink3"
          >
            {pending ? "Asking…" : "Ask the coach"}
          </button>
        </div>
        {models && models.length > 0 && (
          <ModelPicker models={models} value={modelId} onChange={choose} disabled={pending !== null} />
        )}
        {thread.length === 0 && !pending && (
          <div className="mt-8">
            <div className="smallcaps text-ink3">Or start from one of these</div>
            <ul className="mt-2 space-y-1.5">
              {starters(s).map((q) => (
                <li key={q}>
                  <button
                    onClick={() => {
                      setDraft(q);
                      box.current?.focus();
                    }}
                    className="text-left text-[15px] text-ink2 underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink3"
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[13px] text-ink3">These only fill the box; nothing is sent until you press Ask.</p>
          </div>
        )}
      </section>
    </Layout>
  );
}
