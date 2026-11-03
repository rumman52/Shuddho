type RukhHomeProps = { coworkerEnabled: boolean };

function ArrowIcon() {
  return <svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="M5 15 15 5M6 5h9v9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function CoworkerIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M8.2 10.1a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z" stroke="currentColor" strokeWidth="1.5" /><path d="M2.8 19.1c.4-3.2 2.2-4.8 5.4-4.8 1.3 0 2.4.3 3.2.9M15.7 10.1a2.7 2.7 0 1 0 0-5.4M14.7 14.5c3.8-.7 6.1.9 6.5 4.6h-5.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><path d="m13.4 12.2 1.5 1.5 3-3.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function EditorIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M6 3.8h8l4 4v12.4H6V3.8Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M14 3.8v4.4h4M9 12h6M9 15.5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>;
}
function FlowDocumentIcon() {
  return <svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="M5 2.8h6.5L15 6.3v10.9H5V2.8Z" stroke="currentColor" strokeWidth="1.35" strokeLinejoin="round" /><path d="M11.5 2.8v3.5H15M7.5 9.5h5M7.5 12.2h5" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" /></svg>;
}
function StepArrowIcon() {
  return <svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="M4 10h11M11 6l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function RukhHome({ coworkerEnabled }: RukhHomeProps) {
  return (
    <div className="rukh-home">
      <header className="rukh-home-header">
        <a className="rukh-home-brand" href="/" aria-label="Rukh AI workspace home">
          <span className="rukh-home-mark" aria-hidden="true">r</span>
          <span className="rukh-home-brand-copy"><strong>Rukh AI</strong><small>Workspace</small></span>
        </a>
        <nav className="rukh-home-nav" aria-label="Workspace navigation">
          {coworkerEnabled ? <a href="/coworker">AI Coworker</a> : <span className="rukh-home-nav-disabled" aria-disabled="true">Co-workers <small>Preview</small></span>}
          <a href="/editor">Web Editor</a>
        </nav>
        <a className="rukh-home-header-action" href="/editor">Open Web Editor <ArrowIcon /></a>
      </header>

      <main className="rukh-home-main">
        <section className="rukh-home-intro" aria-labelledby="rukh-home-title">
          <div className="rukh-home-intro-copy">
            <h1 id="rukh-home-title">Think clearly. Move work forward.</h1>
            <p>Rukh brings thoughtful writing and hands-on work into one place. Choose the workspace that fits what you need to do next.</p>
          </div>
          <aside className="rukh-home-intro-note" aria-label="Rukh AI approach">
            <p>Writing and execution,<br />connected.</p>
            <span>RUKH AI / WORKSPACE</span>
          </aside>
        </section>

        <section className="rukh-home-products" aria-label="Choose a workspace">
          <article className="rukh-home-product rukh-home-product--coworkers">
            <div className="rukh-home-product-top">
              <span className="rukh-home-product-icon"><CoworkerIcon /></span>
              <span className={coworkerEnabled ? "rukh-home-product-status rukh-home-product-status--active" : "rukh-home-product-status"}>{coworkerEnabled ? "Available" : "Staged release"}</span>
            </div>
            <div className="rukh-home-product-copy">
              <h2>AI Coworker</h2>
              <p>Delegate multi-step work to an AI teammate that keeps the brief, source files and conversation together. Review each result before deciding what happens next.</p>
            </div>
            <div className="rukh-home-flow">
              <p className="rukh-home-flow-title">From brief to review</p>
              <ol className="rukh-home-flow-list" aria-label="Illustrative Co-workers workflow">
                <li className="rukh-home-flow-step">
                  <span className="rukh-home-flow-symbol"><FlowDocumentIcon /></span>
                  <span className="rukh-home-flow-copy"><strong>Understand the brief</strong><small>Keep context and source material together</small></span>
                  <span className="rukh-home-flow-state"><StepArrowIcon /></span>
                </li>
                <li className="rukh-home-flow-step">
                  <span className="rukh-home-flow-symbol"><CoworkerIcon /></span>
                  <span className="rukh-home-flow-copy"><strong>Prepare the work</strong><small>Organize, research and draft</small></span>
                  <span className="rukh-home-flow-state"><StepArrowIcon /></span>
                </li>
                <li className="rukh-home-flow-step">
                  <span className="rukh-home-flow-symbol"><EditorIcon /></span>
                  <span className="rukh-home-flow-copy"><strong>Bring it back for review</strong><small>You decide what happens next</small></span>
                  <span className="rukh-home-flow-state"><StepArrowIcon /></span>
                </li>
              </ol>
            </div>
            <div className="rukh-home-product-footer">
              <p>{coworkerEnabled ? "Your brief stays connected to the work." : "Access is limited while the staged release continues."}</p>
              {coworkerEnabled ? <a className="rukh-home-action" href="/coworker">Open AI Coworker <ArrowIcon /></a> : <button className="rukh-home-action rukh-home-action--disabled" type="button" disabled>Private preview</button>}
            </div>
          </article>

          <article className="rukh-home-product rukh-home-product--editor">
            <div className="rukh-home-product-top">
              <span className="rukh-home-product-icon"><EditorIcon /></span>
              <span className="rukh-home-product-status rukh-home-product-status--active">Available</span>
            </div>
            <div className="rukh-home-product-copy">
              <h2>Web Editor</h2>
              <p>Write and refine in a multilingual workspace with spelling, grammar, clarity and contextual AI review alongside your draft.</p>
            </div>
            <div className="rukh-home-editor-preview" aria-hidden="true">
              <div className="rukh-home-editor-preview-heading"><span>UNTITLED DOCUMENT</span><span>DRAFT</span></div>
              <h3>A thought, made clear.</h3>
              <p>Good writing gives an idea the structure it needs to travel. Refine the words without losing the meaning.</p>
              <div className="rukh-home-editor-preview-checks" aria-label="Writing review features"><span>Spelling</span><span>Grammar</span><span>Clarity</span></div>
            </div>
            <div className="rukh-home-product-footer">
              <p>Keep the words, tone and final edit in your hands.</p>
              <a className="rukh-home-action" href="/editor">Open Web Editor <ArrowIcon /></a>
            </div>
          </article>
        </section>

        <footer className="rukh-home-footer">
          <span className="rukh-home-footer-brand">Rukh AI</span>
          <p>Thoughtful writing. Work that moves forward.</p>
          <span className="rukh-home-footer-note">A workspace built around your next step.</span>
        </footer>
      </main>
    </div>
  );
}
