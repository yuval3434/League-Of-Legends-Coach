// Who the sentences are about. The owner reads "You farm less"; anyone else
// reads "Ana farms less". Every page words its subject through here.

import type { Player } from "./api";

export type Subject = { you: boolean; name: string };

export const YOU: Subject = { you: true, name: "You" };

export function subjectOf(player: Pick<Player, "is_owner" | "game_name">): Subject {
  return player.is_owner ? YOU : { you: false, name: player.game_name };
}

/** "You" or "Ana", to start a sentence or label a bar. */
export function who(s: Subject): string {
  return s.you ? "You" : s.name;
}

/** "you" or "Ana", inside a sentence. */
export function whoLower(s: Subject): string {
  return s.you ? "you" : s.name;
}

/** "You're" or "Ana is". */
export function whoIs(s: Subject): string {
  return s.you ? "You're" : `${s.name} is`;
}

/** "your" or "Ana's". */
export function whose(s: Subject): string {
  return s.you ? "your" : `${s.name}'s`;
}

/** "Your" or "Ana's", to start a sentence. */
export function Whose(s: Subject): string {
  return s.you ? "Your" : `${s.name}'s`;
}

/** The verb agreeing with the subject: "farm" for you, "farms" for Ana. */
export function verb(s: Subject, base: string): string {
  if (s.you) return base;
  return base === "have" ? "has" : `${base}s`;
}
