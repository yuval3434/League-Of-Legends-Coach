// A benchmark pull for one cohort: what it will take, the button, and how far a
// running pull has got. The pull is free, but it uses the Riot call budget, so
// no manual sync can run meanwhile; auto-sync carries on.

import type { CohortOffer, PullStatus, Role } from "../api";
import { pullPlan, pullProgress, roleTab } from "../offers";

export function RoleTabs({ roles, role, onChange }: { roles: Role[]; role: Role; onChange: (role: Role) => void }) {
  if (roles.length < 2) return null;
  return (
    <div role="radiogroup" aria-label="Role" className="mt-8 flex flex-wrap gap-x-1 gap-y-2">
      {roles.map((r) => {
        const on = r === role;
        return (
          <button
            key={r}
            role="radio"
            aria-checked={on}
            onClick={() => onChange(r)}
            className={`rounded-[3px] px-3 py-1.5 text-[14px] ${on ? "bg-ink text-page" : "text-ink2 hover:bg-panel hover:text-ink"}`}
          >
            {roleTab(r)}
          </button>
        );
      })}
    </div>
  );
}

export function PullOffer({
  offer,
  status,
  onStart,
  error,
}: {
  offer: CohortOffer;
  status: PullStatus;
  onStart: (more: boolean) => void;
  error: string | null;
}) {
  const plan = pullPlan(offer);
  const progress = pullProgress(status, offer);
  const running = status.state === "running";
  const ours = status.cohort === offer.cohort;
  return (
    <div className="mt-8 max-w-[700px] rounded-[3px] border border-rule bg-panel/40 px-5 py-4">
      <p className="text-[15px] text-ink2">{plan.text}</p>
      {offer.why_no_pull ? (
        <p className="mt-3 text-[14px] text-ink3">{offer.why_no_pull}</p>
      ) : (
        <button
          onClick={() => onStart(plan.more)}
          disabled={running}
          className="mt-4 rounded-[3px] bg-ink px-5 py-2.5 text-[14px] font-medium text-page hover:bg-ink2 disabled:cursor-not-allowed disabled:bg-rule disabled:text-ink3"
        >
          {plan.button}
        </button>
      )}
      {progress && <p className="mt-3 font-mono text-[12px] text-ink2">{progress}</p>}
      {running && !ours && <p className="mt-3 text-[13px] text-ink3">Another benchmark pull is running; one runs at a time.</p>}
      {error && <p className="mt-3 text-[13px] text-ink2">{error}</p>}
      <p className="mt-3 text-[12px] text-ink3">
        Free, but it uses the Riot call budget: no manual sync can run until it ends, while auto-sync carries on. It
        can stop when the development key expires, and carries on from there next time.
      </p>
    </div>
  );
}
