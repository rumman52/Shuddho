export function RukhMark({ size = "md", className = "" }: { size?: "sm" | "md" | "lg"; className?: string }) {
  return <span className={`rukh-mark rukh-mark--${size} ${className}`} aria-hidden="true">শ</span>;
}
