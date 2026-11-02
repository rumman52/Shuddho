export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";
export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: React.ReactNode }) {
  return <span className={`rukh-badge rukh-badge--${tone}`}>{children}</span>;
}
