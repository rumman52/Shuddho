import { COMPETITION_DEMO_DISCLOSURE, COMPETITION_DEMO_TITLE, competitionDemoFixtures, type CompetitionDemoFixture } from "../lib/competitionDemo";

type Props = {
  selectedFixtureId: string | null;
  onSelectFixture: (fixtureId: string | null) => void;
  onLoadExample: (fixture: CompetitionDemoFixture) => void;
  onRunDemoReview: () => void;
  onResetExample: () => void;
  onTryOwnText: () => void;
  reviewDurationMs: number | null;
};

export function CompetitionDemoPanel({ selectedFixtureId, onSelectFixture, onLoadExample, onRunDemoReview, onResetExample, onTryOwnText, reviewDurationMs }: Props) {
  const selectedFixture = competitionDemoFixtures.find((fixture) => fixture.id === selectedFixtureId) ?? competitionDemoFixtures[0];
  return (
    <section className="competition-demo-panel" aria-label="Competition Demo Examples">
      <div className="competition-demo-panel__header">
        <div>
          <p className="eyebrow">Competition Demo Examples</p>
          <h2>{COMPETITION_DEMO_TITLE}</h2>
        </div>
        <span className="runtime-chip runtime-chip--info">Offline demo · Local engine</span>
      </div>
      <p className="quiet-note">{COMPETITION_DEMO_DISCLOSURE}</p>
      <div className="competition-demo-grid" role="list">
        {competitionDemoFixtures.map((fixture) => (
          <button
            key={fixture.id}
            type="button"
            className={fixture.id === selectedFixture.id ? "competition-demo-card competition-demo-card--active" : "competition-demo-card"}
            onClick={() => onSelectFixture(fixture.id)}
          >
            <strong>{shortTitle(fixture.role)}</strong>
            <span>{fixture.title}</span>
          </button>
        ))}
        <button type="button" className="competition-demo-card" onClick={onTryOwnText}>
          <strong>Try Your Own Text</strong>
          <span>Return to normal writing without prepared fixtures.</span>
        </button>
      </div>
      {selectedFixture ? (
        <div className="competition-demo-detail">
          <p><strong>Role:</strong> {roleLabel(selectedFixture.role)}</p>
          <p>{selectedFixture.description}</p>
          <p><strong>Intentional corrections:</strong> {selectedFixture.annotations.length + 8}+ local checks</p>
          <div className="review-actions">
            <button type="button" className="button-secondary" onClick={() => onLoadExample(selectedFixture)}>Load example</button>
            <button type="button" className="button-primary" onClick={onRunDemoReview}>Run Demo Review</button>
            <button type="button" className="text-button" onClick={onResetExample}>Reset example</button>
          </div>
          {reviewDurationMs !== null ? <p className="quiet-note">Last local demo review: {reviewDurationMs.toFixed(1)} ms</p> : null}
        </div>
      ) : null}
    </section>
  );
}

function shortTitle(role: CompetitionDemoFixture["role"]): string {
  if (role === "student") return "Student Essay";
  if (role === "journalist") return "News Report";
  return "Official Report";
}

function roleLabel(role: CompetitionDemoFixture["role"]): string {
  if (role === "student") return "Student";
  if (role === "journalist") return "Journalist";
  return "Government officer";
}
