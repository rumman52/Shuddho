import { Editor } from '../components/Editor';

const metrics = [
  { label: 'Bangla NLP checks', value: '4 layers' },
  { label: 'Review latency target', value: '< 500ms' },
  { label: 'Privacy posture', value: 'Local-first' },
];

export default function Page() {
  return <main className="shell">
    <section className="hero" aria-labelledby="page-title">
      <div className="hero__copy">
        <p className="eyebrow"><span className="pulse" aria-hidden="true" /> Shuddho Intelligence Platform</p>
        <h1 id="page-title">Professional Bangla writing intelligence for high-stakes teams.</h1>
        <p className="hero__lead">A polished AI workspace that combines instant quality signals, review-ready suggestions, and a privacy-first editing flow built for modern product, policy, and research teams.</p>
        <div className="hero__actions" aria-label="Product highlights">
          <span>Enterprise-grade review</span>
          <span>Context aware correction</span>
          <span>Decision audit trail</span>
        </div>
      </div>
      <div className="hero__panel" aria-label="System health summary">
        <div className="orbit" aria-hidden="true"><span /><span /><span /></div>
        <p>AI quality engine</p>
        <strong>Live document intelligence</strong>
        <small>Secure checks · Human controlled approvals · Sync-ready state</small>
      </div>
    </section>

    <section className="metrics" aria-label="Platform metrics">
      {metrics.map((metric) => <article className="metric" key={metric.label}>
        <strong>{metric.value}</strong>
        <span>{metric.label}</span>
      </article>)}
    </section>

    <Editor />
  </main>;
}
