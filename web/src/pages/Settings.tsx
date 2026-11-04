// API keys. Write-only: the page shows a key's last 4 characters and age, and a
// new key is tested with one cheap call before the server saves it to .env.

import { useEffect, useState } from "react";

import { api, type KeyInfo, type KeyName } from "../api";
import { Layout } from "../components/Layout";
import { keyStatus, shortTime } from "../keys";

const KEYS: { name: KeyName; title: string; about: string; get: string; test: string }[] = [
  {
    name: "riot",
    title: "Riot API key",
    about: "Syncs players' matches and the benchmarks. Free. Development keys expire 24 hours after you make them.",
    get: "https://developer.riotgames.com",
    test: "Tested with one call to Riot's server status, through the rate limiter.",
  },
  {
    name: "anthropic",
    title: "Anthropic API key",
    about: "Answers coach questions with Claude. Each question is a paid call, so set a spending limit in the console.",
    get: "https://console.anthropic.com",
    test: "Tested by listing models, which is free and uses no tokens.",
  },
];

const TONE = { ok: "text-ink2", warn: "text-accent", off: "text-ink3" };

function KeyForm({ name, title, about, get, test, info, onSaved }: (typeof KEYS)[number] & {
  info: KeyInfo | undefined;
  onSaved: (info: KeyInfo) => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const status = info ? keyStatus(info) : null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const saved = await api.setKey(name, value.trim());
      onSaved(saved);
      setMessage({ ok: true, text: "Tested and saved. It's in use now." });
    } catch (error) {
      setMessage({ ok: false, text: (error as Error).message });
    } finally {
      // The field is cleared either way: the key never lingers on the page.
      setValue("");
      setBusy(false);
    }
  }

  return (
    <section className="border-t border-rule pt-6">
      <div className="grid gap-x-10 gap-y-4 md:grid-cols-[260px_1fr]">
        <div>
          <h2 className="text-[17px] text-ink">{title}</h2>
          <p className="mt-1.5 text-[14px] text-ink3">{about}</p>
          <a href={get} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[13px] text-ink2 underline decoration-rule underline-offset-4 hover:text-ink">
            Get a key
          </a>
        </div>
        <div className="max-w-[560px]">
          <div className="smallcaps text-ink3">Now</div>
          <p className={`mt-1 text-[15px] ${status ? TONE[status.tone] : "text-ink3"}`}>
            {status ? status.words : "Loading…"}
          </p>
          {info?.set_at && <p className="mt-0.5 text-[13px] text-ink3">Set {shortTime(info.set_at)}</p>}
          <form onSubmit={save} className="mt-5">
            <label htmlFor={`${name}-key`} className="smallcaps text-ink3">
              Replace it
            </label>
            <div className="mt-2 flex flex-wrap gap-3">
              <input
                id={`${name}-key`}
                type="password"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="Paste the new key"
                className="min-w-[260px] flex-1 rounded-[3px] border border-rule bg-panel px-4 py-2.5 font-mono text-[14px] text-ink placeholder:font-sans placeholder:text-faint focus:border-ink3 focus:outline-none"
              />
              <button
                type="submit"
                disabled={busy || !value.trim()}
                className="rounded-[3px] bg-ink px-5 py-2.5 text-[14px] font-medium text-page hover:bg-ink2 disabled:cursor-not-allowed disabled:bg-rule disabled:text-ink3"
              >
                {busy ? "Testing…" : "Test and save"}
              </button>
            </div>
            <p className="mt-2 text-[13px] text-ink3">{test}</p>
            {message && (
              <p className={`mt-3 text-[14px] ${message.ok ? "text-ink" : "text-accent"}`} role="status">
                {message.text}
              </p>
            )}
          </form>
        </div>
      </div>
    </section>
  );
}

export function Settings() {
  const [keys, setKeys] = useState<Record<KeyName, KeyInfo> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.keys().then(setKeys).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Layout active="settings">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Settings</div>
        <h1 className="display mt-1.5 max-w-[920px] text-[50px] leading-[1.02]">API keys</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          Keys are saved to <code className="font-mono text-[14px] text-ink">.env</code> on this computer and used at once,
          without restarting anything. They're never shown again: this page only knows each key's last 4 characters and
          when it was set. Settings can only be changed from this computer.
        </p>
      </div>
      {error && <p className="mt-10 text-ink2">{error}</p>}
      <div className="mt-12 space-y-12">
        {KEYS.map((k) => (
          <KeyForm
            key={k.name}
            {...k}
            info={keys?.[k.name]}
            onSaved={(info) => setKeys((all) => (all ? { ...all, [k.name]: info } : all))}
          />
        ))}
      </div>
    </Layout>
  );
}
