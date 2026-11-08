// A coach reply in Markdown. With citations, each cited number arrives as a
// [number](cite:i) link; it shows as the number, and hovering or focusing it
// shows the tool-result field it was copied from. Other links show as text.

import Markdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { CoachAnswer } from "../api";
import { citationFor } from "../coach";

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

function keepCitations(url: string): string {
  return url.startsWith("cite:") ? url : defaultUrlTransform(url);
}

export function CoachReply({ answer }: { answer: Pick<CoachAnswer, "text" | "linked_text" | "citations"> }) {
  const citations = answer.citations ?? [];
  const components: Components = {
    ...MARKDOWN,
    a: ({ href, children }) => {
      const source = citationFor(href, citations);
      if (!source) return <span className="text-ink">{children}</span>;
      return (
        <span
          tabIndex={0}
          className="group/cite relative cursor-help underline decoration-rule decoration-dotted underline-offset-4 outline-none hover:decoration-ink3 focus:decoration-ink3"
        >
          {children}
          <span
            role="tooltip"
            className="pointer-events-none absolute bottom-full left-0 z-10 mb-1.5 w-max max-w-[340px] rounded-[3px] border border-rule bg-panel px-3 py-2 text-left font-mono text-[12px] leading-relaxed text-ink2 opacity-0 shadow-lg shadow-black/40 transition-opacity duration-150 group-hover/cite:opacity-100 group-focus/cite:opacity-100"
          >
            {source}
          </span>
        </span>
      );
    },
  };
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components} urlTransform={keepCitations}>
      {answer.linked_text || answer.text}
    </Markdown>
  );
}
