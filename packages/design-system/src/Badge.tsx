import type { ReactNode } from "react";
export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";
export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`rukh-badge rukh-badge--${tone}`}>{children}</span>;
}
