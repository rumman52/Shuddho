import type { OverlayState } from "./types";

export class IssueOverlay {
  private readonly host: HTMLDivElement;
  private readonly shadowRoot: ShadowRoot;
  private readonly badge: HTMLButtonElement;
  private readonly rail: HTMLDivElement;
  private readonly panel: HTMLDivElement;
  private target: HTMLElement | null = null;
  private visible = false;

  constructor() {
    this.host = document.createElement("div");
    this.host.style.position = "fixed";
    this.host.style.inset = "0";
    this.host.style.pointerEvents = "none";
    this.host.style.zIndex = "2147483646";
    document.documentElement.appendChild(this.host);

    this.shadowRoot = this.host.attachShadow({ mode: "open" });
    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <style>
        .root {
          position: fixed;
          pointer-events: none;
          font-family: "Segoe UI", sans-serif;
        }
        .badge {
          pointer-events: auto;
          border: none;
          border-radius: 999px;
          background: #0f6d62;
          color: white;
          padding: 6px 10px;
          font-size: 12px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.18);
          cursor: pointer;
        }
        .rail {
          margin-top: 6px;
          display: flex;
          gap: 2px;
          height: 6px;
          border-radius: 999px;
          background: rgba(15, 109, 98, 0.14);
          overflow: hidden;
        }
        .tick {
          position: absolute;
          height: 6px;
          border-radius: 999px;
          background: rgba(184, 50, 74, 0.85);
        }
        .rail-inner {
          position: relative;
          width: 100%;
          height: 6px;
        }
        .panel {
          display: none;
          margin-top: 8px;
          width: 280px;
          pointer-events: auto;
          background: white;
          border: 1px solid rgba(18, 32, 48, 0.1);
          border-radius: 16px;
          box-shadow: 0 18px 48px rgba(0,0,0,0.18);
          padding: 10px;
          color: #1f2a37;
        }
        .panel.open {
          display: block;
        }
        .item + .item {
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid rgba(18, 32, 48, 0.08);
        }
        .muted {
          color: #5b6470;
          font-size: 12px;
        }
      </style>
      <div class="root">
        <button class="badge" type="button">Shuddho</button>
        <div class="rail"><div class="rail-inner"></div></div>
        <div class="panel"></div>
      </div>
    `;
    this.shadowRoot.appendChild(wrapper);
    this.badge = this.shadowRoot.querySelector(".badge") as HTMLButtonElement;
    this.rail = this.shadowRoot.querySelector(".rail-inner") as HTMLDivElement;
    this.panel = this.shadowRoot.querySelector(".panel") as HTMLDivElement;

    this.badge.addEventListener("click", () => {
      this.panel.classList.toggle("open");
    });
  }

  render(target: HTMLElement, state: OverlayState): void {
    this.target = target;
    this.visible = true;
    this.syncPosition();
    this.badge.textContent = `${state.ranges.length} issue${state.ranges.length === 1 ? "" : "s"}`;
    this.rail.replaceChildren();
    this.panel.replaceChildren();

    for (const range of state.ranges.slice(0, 8)) {
      const tick = document.createElement("div");
      tick.className = "tick";
      const left = state.textLength > 0 ? (range.start / state.textLength) * 100 : 0;
      const width = Math.max(5, ((range.end - range.start) / Math.max(state.textLength, 1)) * 100);
      tick.style.left = `${Math.min(left, 96)}%`;
      tick.style.width = `${Math.min(width, 28)}%`;
      this.rail.appendChild(tick);

      const item = document.createElement("div");
      item.className = "item";
      item.innerHTML = `
        <strong>${escapeHtml(range.suggestion.original_text)}</strong>
        <div class="muted">${escapeHtml(range.suggestion.explanation_bn)}</div>
      `;
      this.panel.appendChild(item);
    }
  }

  hide(): void {
    this.visible = false;
    (this.shadowRoot.querySelector(".root") as HTMLElement).style.display = "none";
  }

  syncPosition(): void {
    const root = this.shadowRoot.querySelector(".root") as HTMLElement;
    if (!this.target || !this.visible) {
      root.style.display = "none";
      return;
    }

    const rect = this.target.getBoundingClientRect();
    root.style.display = "block";
    root.style.left = `${Math.max(rect.left, 8)}px`;
    root.style.top = `${Math.max(rect.top - 18, 8)}px`;
    root.style.width = `${Math.max(Math.min(rect.width, 360), 120)}px`;
  }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"]/g, (character) => {
    switch (character) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case "\"":
        return "&quot;";
      default:
        return character;
    }
  });
}

