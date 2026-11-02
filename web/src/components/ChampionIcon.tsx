import { useState } from "react";

import { useChampionIcon } from "../ddragon";

/** A champion's square icon, or a monogram if Data Dragon can't be reached. */
export function ChampionIcon({ champion, size = 32 }: { champion: string; size?: number }) {
  const url = useChampionIcon(champion);
  const [failed, setFailed] = useState(false);
  const style = { width: size, height: size };
  if (!url || failed) {
    return (
      <div
        style={style}
        className="flex shrink-0 items-center justify-center rounded-[3px] bg-panel font-mono text-[11px] text-ink3"
        aria-label={champion}
      >
        {champion.slice(0, 2)}
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={champion}
      style={style}
      className="shrink-0 rounded-[3px] ring-1 ring-rule"
      onError={() => setFailed(true)}
    />
  );
}
