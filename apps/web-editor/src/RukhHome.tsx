import ThemeToggle from "./components/ThemeToggle";

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
function CodeIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="m8.5 7-5 5 5 5M15.5 7l5 5-5 5M14 4l-4 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function WritingIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M4 20h4L19.2 8.8a2.8 2.8 0 0 0-4-4L4 16v4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="m13.8 6.2 4 4M4 20l5-1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>;
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
          <a href="/coworker">AI Coworker</a>
          <a href="/fly">Fly</a>
          <a href="/editor">Web Editor</a>
          <a href="/writing">Writing Assistant</a>
        </nav>
        <ThemeToggle />
        <a className="rukh-home-header-action" href="/coworker">Open AI Coworker <ArrowIcon /></a>
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
              <span className={coworkerEnabled ? "rukh-home-product-status rukh-home-product-status--active" : "rukh-home-product-status"}>{coworkerEnabled ? "Available" : "Account required"}</span>
            </div>
            <div className="rukh-home-product-copy">
              <h2>AI Coworker</h2>
              <p>Delegate multi-step work to an AI teammate that keeps the brief, source files and conversation together. Review each result before deciding what happens next.</p>
            </div>
            <div className="rukh-home-flow">
              <p className="rukh-home-flow-title">From brief to review</p>
              <ol className="rukh-home-flow-list" aria-label="Illustrative AI Coworker workflow">
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
              <p>Sign in to access your conversations and available workspace services.</p>
              <a className="rukh-home-action" href="/coworker">Open AI Coworker <ArrowIcon /></a>
            </div>
          </article>

          <article className="rukh-home-product rukh-home-product--fly">
            <div className="rukh-home-product-top">
              <span className="rukh-home-product-icon"><CodeIcon /></span>
              <span className="rukh-home-product-status rukh-home-product-status--active">Workspace available</span>
            </div>
            <div className="rukh-home-product-copy">
              <h2>Fly</h2>
              <p>A dedicated coding workspace for multi-file source drafts, private file saving, isolated HTML previews and Rukh code review. Python 3.11 execution is available only when the isolated sandbox is enabled; other language runtimes and Git repository access are not connected yet.</p>
            </div>
            <div className="rukh-home-code-preview" aria-label="Fly code workspace preview">
              <div><span>main.py</span><small>PYTHON SOURCE</small></div>
              <pre><code>def main():{"\n"}    print("Hello from Fly"){"\n"}{"\n"}main()</code></pre>
              <small>EDIT · RUN · REVIEW</small>
            </div>
            <div className="rukh-home-product-footer">
              <p>Local drafts remain in this browser tab until saved to Rukh Files.</p>
              <a className="rukh-home-action" href="/fly">Open Fly <ArrowIcon /></a>
            </div>
          </article>

          <article className="rukh-home-product rukh-home-product--editor">
            <div className="rukh-home-product-top">
              <span className="rukh-home-product-icon"><EditorIcon /></span>
              <span className="rukh-home-product-status rukh-home-product-status--active">Available</span>
            </div>
            <div className="rukh-home-product-copy">
              <h2>Web Editor</h2>
              <p>Design and refine websites with visual layers, HTML source editing and an isolated preview. Saving stores a private source file; it does not publish your website.</p>
            </div>
            <div className="rukh-home-editor-preview" aria-hidden="true">
              <div className="rukh-home-editor-preview-heading"><span>WEBSITE CANVAS</span><span>PRIVATE DRAFT</span></div>
              <h3>Your next page, in view.</h3>
              <p>Shape a layout, inspect HTML and CSS, and review the isolated preview before exporting.</p>
              <div className="rukh-home-editor-preview-checks" aria-label="Website editor features"><span>HTML</span><span>CSS</span><span>Preview</span></div>
            </div>
            <div className="rukh-home-product-footer">
              <p>Preview and refine your website without publishing it.</p>
              <a className="rukh-home-action" href="/editor">Open Web Editor <ArrowIcon /></a>
            </div>
          </article>

          <article className="rukh-home-product rukh-home-product--writing">
            <div className="rukh-home-product-top">
              <span className="rukh-home-product-icon"><WritingIcon /></span>
              <span className="rukh-home-product-status rukh-home-product-status--active">Available</span>
            </div>
            <div className="rukh-home-product-copy">
              <h2>Writing Assistant</h2>
              <p>Refine multilingual writing with spelling, grammar, punctuation, clarity and contextual AI suggestions. Review, apply or dismiss changes while preserving the original meaning and tone.</p>
            </div>
            <div className="rukh-home-editor-preview">
              <div className="rukh-home-editor-preview-heading"><span>WRITING STUDIO</span><span>REVIEW</span></div>
              <h3>A thought, made clear.</h3>
              <p>Improve the sentence without losing the original meaning or tone.</p>
              <div className="rukh-home-editor-preview-checks"><span>Spelling</span><span>Grammar</span><span>Clarity</span></div>
            </div>
            <div className="rukh-home-product-footer">
              <p>Keep the words, tone and final edit in your hands.</p>
              <a className="rukh-home-action" href="/writing">Open Writing Assistant <ArrowIcon /></a>
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
