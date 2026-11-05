import NavigationIcon from "./WorkspaceNavigationIcon";

// Geometry and colors from the companion mark in the approved design export.
export function RukhCompanionMark() {
  return <svg className="rukh-companion-mark" width="60" height="60" viewBox="0 0 60 60" aria-hidden="true">
    <rect width="60" height="60" rx="20.4" fill="var(--rukh-accent-soft)" />
    <svg x="9" y="9" width="42" height="42" viewBox="0 0 32 32">
      <path d="M4 22 L14 6 L17 17 L28 10 L22 27 L16 22 L9 27 Z" fill="var(--rukh-accent)" />
      <circle cx="15" cy="14" r="1.3" fill="#FFFFFF" />
    </svg>
  </svg>;
}

const starters = [
  { icon: "target", label: "Plan a project", mobile: "Plan my next project", description: "Turn an idea into next steps", ariaLabel: "Start with a work plan", prompt: "Break this goal into a practical plan with next steps: " },
  { icon: "layout", label: "Build a website", mobile: "Build a beautiful website", description: "Bring your next idea to life", ariaLabel: "Start with a website brief", prompt: "Help me plan and build a website for: " },
  { icon: "search", label: "Research a topic", mobile: "Research a topic", description: "Get a clear, sourced brief", ariaLabel: "Start with a research brief", prompt: "Research this topic and summarize the findings with sources: " },
];

export default function CoworkerWelcome({ disabled = false, onChoose }: { disabled?: boolean; onChoose: (prompt: string) => void }) {
  return <div className="rukh-welcome">
    <RukhCompanionMark />
    <span className="rukh-welcome-badge">YOUR AI COWORKER</span>
    <h1>What shall we<span className="rukh-welcome-heading-end"> work on today?</span></h1>
    <p>Think it through. Make something. Move it forward.</p>
    <div className="rukh-welcome-starters" aria-label="Conversation starters">
      {starters.map(starter => <button key={starter.icon} type="button" aria-label={starter.ariaLabel} disabled={disabled} onClick={() => onChoose(starter.prompt)}>
        <span className="rukh-welcome-icon"><NavigationIcon name={starter.icon} /></span>
        <strong className="rukh-welcome-desktop-label">{starter.label}</strong>
        <span className="rukh-welcome-mobile-label">{starter.mobile}</span>
        <small>{starter.description}</small>
      </button>)}
    </div>
  </div>;
}
