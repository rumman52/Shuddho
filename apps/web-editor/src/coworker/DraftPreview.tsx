import { useState } from "react";
import type { CoworkerDraft, CoworkerTask, EmailDraft } from "./client";

export function draftTitle(draft: CoworkerDraft): string {
  if ("report" in draft) return draft.report.title;
  if (draft.kind === "email") return draft.email.subject;
  if (draft.kind === "document") return draft.document.title;
  return draft.title;
}

function CopyButton({ text, label = "Copy text" }: { text: string; label?: string }) {
  const [message, setMessage] = useState("");
  return <div className="cw-copy"><button type="button" className="cw-text-button" onClick={async () => {
    try { await navigator.clipboard.writeText(text); setMessage("Copied."); }
    catch { setMessage("Copy is unavailable here. Select the text to copy it."); }
  }}>{label}</button>{message && <span role="status">{message}</span>}</div>;
}

export default function DraftPreview({ draft, sources, preview }: { draft: CoworkerDraft; sources: CoworkerTask["sources"]; preview?: CoworkerTask["preview"] }) {
  const language = { dir: "auto", lang: draft.output_language } as const;
  const references = (ids: string[]) => <p className="cw-reference">{ids.map(id => sources.find(source => source.id === id)?.label ?? id).join(" · ")}</p>;
  const email = (value: EmailDraft) => <><article className="cw-email" {...language}><h3>{value.subject}</h3><p>{value.body}</p></article><CopyButton text={value.subject + "\n\n" + value.body} label="Copy email" /></>;
  if ("report" in draft) return <div className="cw-draft-tabs">
    <details open><summary>Report preview</summary><article className="cw-paper" {...language}>
      <h3>{draft.report.title}</h3><p className="cw-report-summary">{draft.report.summary}</p>
      {draft.report.sections.map((section, index) => <section key={index}><h4>{section.heading}</h4>{section.paragraphs.map((text, index) => <p key={index}>{text}</p>)}{references(section.source_ids)}</section>)}
    </article></details><details open><summary>Email draft</summary>{email(draft.email)}</details>
  </div>;
  if (draft.kind === "email") return <div className="cw-draft-tabs"><details open><summary>Email draft</summary>{email(draft.email)}{references(draft.source_ids)}</details></div>;
  if (draft.kind === "document") return <div className="cw-draft-tabs"><details open><summary>Document preview</summary><article className="cw-paper" {...language}>
    <h3>{draft.document.title}</h3>{draft.document.summary && <p>{draft.document.summary}</p>}
    {draft.document.sections.map((section, index) => <section key={index}>{section.heading && <h4>{section.heading}</h4>}{section.paragraphs.map((text, i) => <p key={i}>{text}</p>)}
      {section.bullets.length > 0 && <ul>{section.bullets.map((text, i) => <li key={i}>{text}</li>)}</ul>}{references(section.source_ids)}</section>)}
  </article><CopyButton text={[draft.document.title, draft.document.summary, ...draft.document.sections.flatMap(section => [section.heading, ...section.paragraphs, ...section.bullets.map(text => "• " + text)])].filter(Boolean).join("\n\n")} label="Copy document" /></details></div>;
  if (draft.kind === "social") return <div className="cw-draft-tabs"><details open><summary>Post drafts</summary>
    {draft.posts.map((post, index) => <section className="cw-post" key={index} aria-label={`Post ${index + 1}`}><div className="cw-post-heading"><span>{post.platform === "facebook" ? "Facebook" : post.platform === "linkedin" ? "LinkedIn" : "Post"}</span><span>Draft</span></div>
      <article className="cw-email" {...language}><h3>{post.label}</h3><p>{post.text}</p>{post.suggested_timing && <p className="cw-plan-meta">{post.suggested_timing}</p>}</article>
      <CopyButton text={post.text} label="Copy post" />{references(post.source_ids)}</section>)}
  </details></div>;
  if (draft.kind === "meeting") return <div className="cw-draft-tabs"><details open><summary>Meeting draft</summary><article className="cw-paper" {...language}>
    <h3>{draft.title}</h3><p>{draft.summary}</p><h4>{draft.labels.notes}</h4>
    {draft.notes.map((note, i) => <section key={i}><p>{note.text}</p>{references(note.source_ids)}</section>)}
    {draft.decisions.length > 0 && <><h4>{draft.labels.decisions}</h4>{draft.decisions.map((item, i) => <section key={i}><p>{item.text}</p>{references(item.source_ids)}</section>)}</>}
    {draft.actions.length > 0 && <><h4>{draft.labels.actions}</h4><ol className="cw-plan-list">{draft.actions.map((action, i) => <li key={i}><p>{action.text}</p><p className="cw-plan-meta">{draft.labels[action.basis]}{action.owner && ` · ${draft.labels.owner}: ${action.owner}`}{action.deadline && ` · ${draft.labels.deadline}: ${action.deadline}`}</p>{references(action.source_ids)}</li>)}</ol></>}
  </article></details></div>;
  if (draft.kind === "presentation") return <div className="cw-draft-tabs"><details open><summary>Presentation preview</summary>
    <p className="cw-fineprint">{draft.slides.length} slides · Editable text and charts in the PPTX. The PDF is a reading handout.</p>
    {draft.slides.map((slide, index) => <article className="cw-paper cw-slide-preview" key={index} {...language} aria-label={`Slide ${index + 1}`}>
      <span className="cw-eyebrow" dir="ltr">{String(index + 1).padStart(2, "0")} / {String(draft.slides.length).padStart(2, "0")}</span><h3>{slide.title}</h3>
      {slide.bullets.length > 0 && <ul>{slide.bullets.map((text, i) => <li key={i}>{text}</li>)}</ul>}
      {slide.chart && <div className="cw-table-scroll" role="region" aria-label={`Slide ${index + 1} chart data`} tabIndex={0}><table><caption>{slide.chart.unit}</caption><thead><tr><th scope="col" aria-label="Category"></th>{slide.chart.series.map((series, i) => <th scope="col" key={i}>{series.label}</th>)}</tr></thead><tbody>{slide.chart.categories.map((category, i) => <tr key={i}><th scope="row">{category}</th>{slide.chart!.series.map((series, j) => <td key={j}>{series.values[i]}</td>)}</tr>)}</tbody></table></div>}
      {slide.speaker_notes && <details><summary>Speaker notes</summary><p>{slide.speaker_notes}</p></details>}{references(slide.source_ids)}
    </article>)}
  </details></div>;
  if (draft.kind === "spreadsheet") {
    const cell = (value: string | number | null, format: string) => value === null ? "—" : typeof value === "string" ? value : format === "percent" ? `${(value * 100).toFixed(1)}%` : format === "integer" ? value.toFixed(0) : value.toFixed(2);
    return <div className="cw-draft-tabs"><details open><summary>Spreadsheet preview</summary><article className="cw-paper" {...language}>
      <h3>{draft.title}</h3><p>{draft.summary}</p>
      {preview ? <div className="cw-table-scroll" role="region" aria-label="Spreadsheet values" tabIndex={0}><table><caption>{draft.sheet_name}</caption><thead><tr>{preview.columns.map(column => <th scope="col" key={column.id}>{column.label}{column.calculated && <small>Calculated</small>}</th>)}</tr></thead><tbody>{preview.rows.map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j}>{cell(value, preview.columns[j].format)}</td>)}</tr>)}</tbody>{draft.summary_label && <tfoot><tr><th colSpan={preview.columns.length}>{draft.summary_label}</th></tr><tr>{preview.totals.map((value, i) => <td key={i}>{cell(value, preview.columns[i].format)}</td>)}</tr></tfoot>}</table></div> : <p>The table preview is unavailable. Download the workbook to review the saved values.</p>}
      {draft.chart && <p className="cw-fineprint">The editable workbook includes a chart: {draft.chart.title}</p>}
      {references(draft.source_ids)}
    </article><p className="cw-fineprint">Download the XLSX to edit inputs and recalculate formulas. A dash means a missing or undefined value. The CSV contains data values; formulas, totals and charts are in the workbook.</p></details></div>;
  }
  return <div className="cw-draft-tabs"><details open><summary>Proposed plan</summary><article className="cw-paper" {...language}>
    <h3>{draft.title}</h3><p>{draft.overview}</p><ol className="cw-plan-list">{draft.items.map((item, i) => <li key={i}>{item.when && <h4>{item.when}</h4>}<p>{item.task}</p><p className="cw-plan-meta">{draft.labels[item.basis]} · {draft.labels[item.priority]}</p>{references(item.source_ids)}</li>)}</ol>
  </article><p className="cw-fineprint">This is a draft plan. Calendar events and reminders have not been created.</p></details></div>;
}
