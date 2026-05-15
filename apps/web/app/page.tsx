import { Editor } from '../components/Editor';

export default function Page() {
  return <main className="shell">
    <header className="header">
      <div>
        <p className="badge">Hybrid client-cloud writing assistant</p>
        <h1>Shuddho Draft Lab</h1>
        <p className="muted">An original AI writing workspace with inline checks, suggestion decisions, and sync-ready document state.</p>
      </div>
      <p className="badge">Privacy-first MVP</p>
    </header>
    <Editor />
  </main>;
}
