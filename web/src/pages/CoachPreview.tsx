// A stand-in until the Coach page is built: it shows the question an
// "Ask the coach" button carried here, so the hand-off can be checked.

import { Layout } from "../components/Layout";

export function CoachPreview({ question }: { question: string }) {
  return (
    <Layout active="coach">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Coach</div>
        <h1 className="display mt-1.5 text-[40px] leading-[1.05]">The coach page comes next</h1>
        {question && (
          <p className="mt-5 max-w-[700px] text-[16px] text-ink2">
            Your question will be waiting in the box: <span className="text-ink">“{question}”</span>
          </p>
        )}
      </div>
    </Layout>
  );
}
