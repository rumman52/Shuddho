import { getEditableSelection, selectEditableRange, supportsInlineMirror } from "./editable";
import type { OverlayState, SuggestionRange } from "./types";

const MAX_RENDERED_RANGES = 48;
const MAX_PANEL_ITEMS = 10;

interface OverlayActions {
  canApplySuggestion: boolean;
  onAccept?: (range: SuggestionRange, replacement: string) => boolean;
  onDismiss?: (range: SuggestionRange) => boolean;
}

export class IssueOverlay {
  private readonly host: HTMLDivElement;
  private readonly shadowRoot: ShadowRoot;
  private readonly root: HTMLDivElement;
  private readonly badge: HTMLButtonElement;
  private readonly rail: HTMLDivElement;
  private readonly panel: HTMLDivElement;
  private readonly panelStatus: HTMLDivElement;
  private readonly prevButton: HTMLButtonElement;
  private readonly nextButton: HTMLButtonElement;
  private readonly activeOriginal: HTMLDivElement;
  private readonly activeReplacement: HTMLDivElement;
  private readonly activeExplanation: HTMLDivElement;
  private readonly activeActions: HTMLDivElement;
  private readonly panelHint: HTMLDivElement;
  private readonly panelList: HTMLDivElement;
  private readonly inlineRoot: HTMLDivElement;
  private readonly inlineContent: HTMLDivElement;
  private target: HTMLElement | null = null;
  private state: OverlayState = { text: "", ranges: [] };
  private activeRangeIndex = -1;
  private visible = false;
  private inlineVisible = false;
  private panelOpen = false;
  private resizeObserver: ResizeObserver | null = null;
  private observedTarget: HTMLElement | null = null;
  private actions: OverlayActions = { canApplySuggestion: false };

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
          height: 8px;
          border-radius: 999px;
          background: rgba(15, 109, 98, 0.14);
          overflow: hidden;
          pointer-events: auto;
        }
        .tick {
          position: absolute;
          height: 8px;
          border: none;
          border-radius: 999px;
          background: rgba(184, 50, 74, 0.76);
          cursor: pointer;
        }
        .tick:hover,
        .tick[data-active="true"] {
          background: rgba(184, 50, 74, 0.96);
          box-shadow: 0 0 0 2px rgba(184, 50, 74, 0.18);
        }
        .tick[data-severity="low"] {
          background: rgba(201, 135, 26, 0.82);
        }
        .tick[data-severity="high"] {
          background: rgba(142, 35, 57, 0.94);
        }
        .rail-inner {
          position: relative;
          width: 100%;
          height: 8px;
        }
        .panel {
          display: none;
          margin-top: 8px;
          width: 320px;
          max-width: min(320px, calc(100vw - 16px));
          pointer-events: auto;
          background: white;
          border: 1px solid rgba(18, 32, 48, 0.1);
          border-radius: 18px;
          box-shadow: 0 18px 48px rgba(0,0,0,0.18);
          padding: 12px;
          color: #1f2a37;
        }
        .panel.open {
          display: block;
        }
        .panel-toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
        }
        .panel-status {
          color: #5b6470;
          font-size: 12px;
        }
        .panel-nav {
          display: flex;
          gap: 6px;
        }
        .nav-button {
          border: 1px solid rgba(18, 32, 48, 0.12);
          background: white;
          color: #1f2a37;
          border-radius: 999px;
          padding: 4px 10px;
          font-size: 12px;
          cursor: pointer;
        }
        .nav-button:disabled {
          opacity: 0.45;
          cursor: default;
        }
        .active-card {
          padding: 10px 12px;
          border-radius: 14px;
          background: rgba(15, 109, 98, 0.08);
        }
        .active-original {
          font-weight: 700;
        }
        .active-replacement {
          margin-top: 6px;
          color: #0f6d62;
          font-weight: 600;
        }
        .active-explanation {
          margin-top: 8px;
        }
        .panel-actions {
          margin-top: 10px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .action-button {
          border-radius: 999px;
          border: 1px solid rgba(18, 32, 48, 0.12);
          padding: 6px 12px;
          font-size: 12px;
          cursor: pointer;
          background: white;
          color: #1f2a37;
        }
        .action-button--primary {
          background: #0f6d62;
          border-color: #0f6d62;
          color: white;
        }
        .action-button--secondary {
          background: #fffaf2;
          border-color: rgba(201, 135, 26, 0.3);
          color: #7a4f00;
        }
        .action-button:disabled {
          opacity: 0.45;
          cursor: default;
        }
        .panel-hint {
          margin-top: 10px;
          line-height: 1.35;
        }
        .panel-list {
          margin-top: 10px;
          display: grid;
          gap: 8px;
          max-height: 220px;
          overflow: auto;
        }
        .item {
          width: 100%;
          border: 1px solid rgba(18, 32, 48, 0.08);
          background: white;
          border-radius: 12px;
          padding: 8px 10px;
          text-align: left;
          cursor: pointer;
        }
        .item[data-active="true"] {
          border-color: rgba(15, 109, 98, 0.26);
          background: rgba(15, 109, 98, 0.08);
        }
        .item strong,
        .item span,
        .item .muted {
          display: block;
        }
        .item span {
          margin-top: 4px;
          color: #0f6d62;
          font-weight: 600;
        }
        .item + .item {
          margin-top: 0;
        }
        .muted {
          color: #5b6470;
          font-size: 12px;
        }
        .inline-root {
          display: none;
          position: fixed;
          pointer-events: none;
          overflow: hidden;
          border-radius: 10px;
        }
        .inline-content {
          position: absolute;
          inset: 0 auto auto 0;
          box-sizing: border-box;
          color: transparent;
          white-space: pre-wrap;
          overflow-wrap: break-word;
          word-break: break-word;
        }
        .inline-content--single-line {
          white-space: pre;
          overflow-wrap: normal;
          word-break: normal;
        }
        .inline-fragment {
          color: transparent;
          border-radius: 4px;
          box-decoration-break: clone;
          -webkit-box-decoration-break: clone;
        }
        .inline-fragment--issue {
          box-shadow: inset 0 -2px 0 rgba(184, 50, 74, 0.74);
          background:
            linear-gradient(180deg, transparent 60%, rgba(184, 50, 74, 0.12) 60%),
            repeating-linear-gradient(
              -55deg,
              rgba(184, 50, 74, 0.88) 0 2px,
              transparent 2px 5px
            );
          background-size: 100% 100%, 10px 4px;
          background-repeat: no-repeat, repeat-x;
          background-position: 0 0, 0 calc(100% - 1px);
        }
        .inline-fragment--low {
          box-shadow: inset 0 -2px 0 rgba(201, 135, 26, 0.78);
          background:
            linear-gradient(180deg, transparent 60%, rgba(201, 135, 26, 0.1) 60%),
            repeating-linear-gradient(
              -55deg,
              rgba(201, 135, 26, 0.9) 0 2px,
              transparent 2px 5px
            );
          background-size: 100% 100%, 10px 4px;
          background-repeat: no-repeat, repeat-x;
          background-position: 0 0, 0 calc(100% - 1px);
        }
        .inline-fragment--high {
          box-shadow: inset 0 -2px 0 rgba(142, 35, 57, 0.88);
          background:
            linear-gradient(180deg, transparent 56%, rgba(142, 35, 57, 0.16) 56%),
            repeating-linear-gradient(
              -55deg,
              rgba(142, 35, 57, 0.96) 0 2px,
              transparent 2px 5px
            );
          background-size: 100% 100%, 10px 4px;
          background-repeat: no-repeat, repeat-x;
          background-position: 0 0, 0 calc(100% - 1px);
        }
        .inline-fragment--active {
          background: linear-gradient(180deg, transparent 46%, rgba(15, 109, 98, 0.2) 46%);
          box-shadow: inset 0 -3px 0 rgba(15, 109, 98, 0.8);
        }
      </style>
      <div class="root">
        <button class="badge" type="button">Shuddho</button>
        <div class="rail"><div class="rail-inner"></div></div>
        <div class="panel">
          <div class="panel-toolbar">
            <div class="panel-status"></div>
            <div class="panel-nav">
              <button class="nav-button nav-button--prev" type="button">Previous</button>
              <button class="nav-button nav-button--next" type="button">Next</button>
            </div>
          </div>
          <div class="active-card">
            <div class="active-original"></div>
            <div class="active-replacement"></div>
            <div class="muted active-explanation"></div>
            <div class="panel-actions"></div>
            <div class="muted panel-hint"></div>
          </div>
          <div class="panel-list"></div>
        </div>
      </div>
      <div class="inline-root">
        <div class="inline-content"></div>
      </div>
    `;
    this.shadowRoot.appendChild(wrapper);
    this.root = this.shadowRoot.querySelector(".root") as HTMLDivElement;
    this.badge = this.shadowRoot.querySelector(".badge") as HTMLButtonElement;
    this.rail = this.shadowRoot.querySelector(".rail-inner") as HTMLDivElement;
    this.panel = this.shadowRoot.querySelector(".panel") as HTMLDivElement;
    this.panelStatus = this.shadowRoot.querySelector(".panel-status") as HTMLDivElement;
    this.prevButton = this.shadowRoot.querySelector(".nav-button--prev") as HTMLButtonElement;
    this.nextButton = this.shadowRoot.querySelector(".nav-button--next") as HTMLButtonElement;
    this.activeOriginal = this.shadowRoot.querySelector(".active-original") as HTMLDivElement;
    this.activeReplacement = this.shadowRoot.querySelector(".active-replacement") as HTMLDivElement;
    this.activeExplanation = this.shadowRoot.querySelector(".active-explanation") as HTMLDivElement;
    this.activeActions = this.shadowRoot.querySelector(".panel-actions") as HTMLDivElement;
    this.panelHint = this.shadowRoot.querySelector(".panel-hint") as HTMLDivElement;
    this.panelList = this.shadowRoot.querySelector(".panel-list") as HTMLDivElement;
    this.inlineRoot = this.shadowRoot.querySelector(".inline-root") as HTMLDivElement;
    this.inlineContent = this.shadowRoot.querySelector(".inline-content") as HTMLDivElement;

    this.badge.addEventListener("click", () => {
      this.setPanelOpen(!this.panelOpen);
    });
    this.prevButton.addEventListener("click", () => {
      this.focusAdjacentIssue(-1);
    });
    this.nextButton.addEventListener("click", () => {
      this.focusAdjacentIssue(1);
    });
  }

  render(target: HTMLElement, state: OverlayState, actions?: OverlayActions): void {
    const targetChanged = this.target !== target;
    this.target = target;
    this.visible = true;
    this.state = normalizeOverlayState(state);
    this.inlineVisible = supportsInlineMirror(target);
    this.actions = actions ?? { canApplySuggestion: false };
    this.observeTarget(target);

    if (this.state.ranges.length === 0) {
      this.activeRangeIndex = -1;
    } else if (targetChanged || this.activeRangeIndex < 0 || this.activeRangeIndex >= this.state.ranges.length) {
      this.activeRangeIndex = this.resolveRangeIndexFromSelection();
    }

    this.badge.textContent = this.state.ranges.length
      ? `Shuddho - ${this.state.ranges.length}`
      : "Shuddho - Clean";

    this.renderRail();
    this.renderPanel();
    if (this.inlineVisible) {
      this.renderInlineMirror(target as HTMLTextAreaElement | HTMLInputElement, this.state);
    } else {
      this.inlineRoot.style.display = "none";
    }
    this.syncPosition();
  }

  hide(): void {
    this.visible = false;
    this.inlineVisible = false;
    this.target = null;
    this.state = { text: "", ranges: [] };
    this.activeRangeIndex = -1;
    this.root.style.display = "none";
    this.inlineRoot.style.display = "none";
    this.setPanelOpen(false);
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.observedTarget = null;
  }

  syncPosition(): void {
    if (!this.target || !this.visible) {
      this.root.style.display = "none";
      this.inlineRoot.style.display = "none";
      return;
    }

    const rect = this.target.getBoundingClientRect();
    const preferredWidth = this.panelOpen ? 320 : Math.max(Math.min(rect.width, 320), 180);
    const rootWidth = Math.min(preferredWidth, Math.max(window.innerWidth - 16, 160));
    this.root.style.display = "block";
    this.root.style.width = `${rootWidth}px`;

    const rootHeight = this.root.getBoundingClientRect().height || (this.panelOpen ? 320 : 44);
    const maxLeft = Math.max(8, window.innerWidth - rootWidth - 8);
    const desiredLeft = rect.right - rootWidth;
    const preferredTop = rect.top - 20;
    const fallbackTop = rect.bottom + 8;
    const maxTop = Math.max(8, window.innerHeight - rootHeight - 8);
    const resolvedTop = preferredTop >= 8 ? clamp(preferredTop, 8, maxTop) : clamp(fallbackTop, 8, maxTop);

    this.root.style.left = `${clamp(desiredLeft, 8, maxLeft)}px`;
    this.root.style.top = `${resolvedTop}px`;

    if (!this.inlineVisible || !supportsInlineMirror(this.target)) {
      this.inlineRoot.style.display = "none";
      return;
    }

    this.inlineRoot.style.display = "block";
    this.inlineRoot.style.left = `${rect.left}px`;
    this.inlineRoot.style.top = `${rect.top}px`;
    this.inlineRoot.style.width = `${rect.width}px`;
    this.inlineRoot.style.height = `${rect.height}px`;
    this.applyInlineTargetStyles(this.target);
  }

  syncSelection(): void {
    if (!this.target || !this.visible || this.state.ranges.length === 0) {
      return;
    }

    const nextIndex = this.resolveRangeIndexFromSelection();
    if (nextIndex === this.activeRangeIndex) {
      this.syncPosition();
      return;
    }

    this.activeRangeIndex = nextIndex;
    this.renderRail();
    this.renderPanel();
    if (supportsInlineMirror(this.target)) {
      this.renderInlineMirror(this.target, this.state);
    }
    this.syncPosition();
  }

  private focusAdjacentIssue(direction: -1 | 1): void {
    if (!this.state.ranges.length) {
      return;
    }

    const currentIndex = this.activeRangeIndex >= 0 ? this.activeRangeIndex : 0;
    const nextIndex = (currentIndex + direction + this.state.ranges.length) % this.state.ranges.length;
    this.focusIssue(nextIndex, true);
  }

  private focusIssue(index: number, openPanel: boolean): void {
    const range = this.state.ranges[index];
    if (!range || !this.target) {
      return;
    }

    this.activeRangeIndex = index;
    if (supportsInlineMirror(this.target)) {
      selectEditableRange(this.target, range.start, range.end);
    }
    if (openPanel) {
      this.setPanelOpen(true);
    }
    this.renderRail();
    this.renderPanel();
    if (supportsInlineMirror(this.target)) {
      this.renderInlineMirror(this.target, this.state);
    }
    this.syncPosition();
  }

  private renderRail(): void {
    this.rail.replaceChildren();
    const totalLength = Math.max(this.state.text.length, 1);

    this.state.ranges.forEach((range, index) => {
      const tick = document.createElement("button");
      tick.type = "button";
      tick.className = "tick";
      tick.dataset.active = index === this.activeRangeIndex ? "true" : "false";
      tick.dataset.severity = range.suggestion.severity;
      tick.title = range.suggestion.original_text;
      const left = (range.start / totalLength) * 100;
      const width = Math.max(4, ((range.end - range.start) / totalLength) * 100);
      tick.style.left = `${Math.min(left, 97)}%`;
      tick.style.width = `${Math.min(width, 28)}%`;
      tick.addEventListener("click", () => {
        this.focusIssue(index, true);
      });
      this.rail.appendChild(tick);
    });
  }

  private renderPanel(): void {
    const activeRange = this.getActiveRange();
    this.panelStatus.textContent = activeRange
      ? `Issue ${this.activeRangeIndex + 1} of ${this.state.ranges.length}`
      : "No active issue";
    this.prevButton.disabled = this.state.ranges.length <= 1;
    this.nextButton.disabled = this.state.ranges.length <= 1;

    if (!activeRange) {
      this.activeOriginal.textContent = "No issues in this field.";
      this.activeReplacement.textContent = "";
      this.activeExplanation.textContent = "Type more Bangla text to analyze this input.";
      this.activeActions.replaceChildren();
      this.panelHint.textContent = "";
      this.panelList.replaceChildren();
      return;
    }

    this.activeOriginal.textContent = activeRange.suggestion.original_text;
    this.activeReplacement.textContent = activeRange.suggestion.replacement_options[0] ?? "No direct replacement";
    this.activeExplanation.textContent = activeRange.suggestion.explanation_bn || activeRange.suggestion.explanation_en;
    this.renderActiveActions(activeRange);
    this.panelHint.textContent = this.actions.canApplySuggestion
      ? "Accept applies directly in this field."
      : activeRange.suggestion.replacement_options.length
        ? "Preview only in rich editors. Direct apply is currently limited to textarea and input fields."
        : "No direct replacement is available for this issue yet.";

    const windowStart = Math.max(0, this.activeRangeIndex - Math.floor(MAX_PANEL_ITEMS / 2));
    const visibleRanges = this.state.ranges.slice(windowStart, windowStart + MAX_PANEL_ITEMS);
    this.panelList.replaceChildren();
    visibleRanges.forEach((range) => {
      const actualIndex = this.state.ranges.indexOf(range);
      const item = document.createElement("button");
      item.type = "button";
      item.className = "item";
      item.dataset.active = actualIndex === this.activeRangeIndex ? "true" : "false";
      item.innerHTML = `
        <strong>${escapeHtml(range.suggestion.original_text)}</strong>
        ${range.suggestion.replacement_options[0] ? `<span>${escapeHtml(range.suggestion.replacement_options[0])}</span>` : ""}
        <div class="muted">${escapeHtml(range.suggestion.explanation_bn || range.suggestion.explanation_en)}</div>
      `;
      item.addEventListener("click", () => {
        this.focusIssue(actualIndex, true);
      });
      this.panelList.appendChild(item);
    });
  }

  private renderInlineMirror(target: HTMLTextAreaElement | HTMLInputElement, state: OverlayState): void {
    this.inlineContent.replaceChildren();
    this.inlineContent.classList.toggle("inline-content--single-line", target instanceof HTMLInputElement);

    let cursor = 0;
    state.ranges.forEach((range, index) => {
      const start = clamp(range.start, 0, state.text.length);
      const end = clamp(range.end, start, state.text.length);
      if (start > cursor) {
        this.inlineContent.appendChild(this.createInlineFragment(state.text.slice(cursor, start)));
      }
      if (end > start) {
        this.inlineContent.appendChild(
          this.createInlineFragment(
            state.text.slice(start, end),
            range,
            index === this.activeRangeIndex,
            index,
          )
        );
      }
      cursor = Math.max(cursor, end);
    });

    if (cursor < state.text.length) {
      this.inlineContent.appendChild(this.createInlineFragment(state.text.slice(cursor)));
    }

    if (!state.text.length) {
      this.inlineContent.appendChild(this.createInlineFragment("\u200b"));
    }

    this.applyInlineTargetStyles(target);
  }

  private createInlineFragment(
    text: string,
    range?: SuggestionRange,
    active = false,
    issueIndex?: number,
  ): HTMLSpanElement {
    const fragment = document.createElement("span");
    const classNames = ["inline-fragment"];
    if (range) {
      classNames.push("inline-fragment--issue", `inline-fragment--${range.suggestion.severity}`);
    }
    if (active) {
      classNames.push("inline-fragment--active");
    }
    fragment.className = classNames.join(" ");
    if (issueIndex !== undefined) {
      fragment.dataset.issueIndex = String(issueIndex);
    }
    fragment.textContent = text || "\u200b";
    return fragment;
  }

  private applyInlineTargetStyles(target: HTMLTextAreaElement | HTMLInputElement): void {
    const styles = window.getComputedStyle(target);
    this.inlineRoot.style.borderRadius = styles.borderRadius;
    this.inlineContent.style.font = styles.font;
    this.inlineContent.style.fontFamily = styles.fontFamily;
    this.inlineContent.style.fontSize = styles.fontSize;
    this.inlineContent.style.fontWeight = styles.fontWeight;
    this.inlineContent.style.fontStyle = styles.fontStyle;
    this.inlineContent.style.lineHeight = styles.lineHeight;
    this.inlineContent.style.letterSpacing = styles.letterSpacing;
    this.inlineContent.style.wordSpacing = styles.wordSpacing;
    this.inlineContent.style.textAlign = styles.textAlign;
    this.inlineContent.style.textIndent = styles.textIndent;
    this.inlineContent.style.textTransform = styles.textTransform;
    this.inlineContent.style.direction = styles.direction;
    this.inlineContent.style.tabSize = styles.tabSize;
    this.inlineContent.style.paddingTop = styles.paddingTop;
    this.inlineContent.style.paddingRight = styles.paddingRight;
    this.inlineContent.style.paddingBottom = styles.paddingBottom;
    this.inlineContent.style.paddingLeft = styles.paddingLeft;
    this.inlineContent.style.width = `${Math.max(target.scrollWidth, target.clientWidth)}px`;
    this.inlineContent.style.minHeight = `${Math.max(target.scrollHeight, target.clientHeight)}px`;
    this.inlineContent.style.transform = `translate(${-target.scrollLeft}px, ${-target.scrollTop}px)`;
  }

  private observeTarget(target: HTMLElement): void {
    if (this.resizeObserver && this.observedTarget === target) {
      return;
    }

    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver(() => {
      this.syncPosition();
    });
    this.resizeObserver.observe(target);
    this.observedTarget = target;
  }

  private resolveRangeIndexFromSelection(): number {
    if (!this.target || this.state.ranges.length === 0) {
      return -1;
    }

    const selection = getEditableSelection(this.target);
    if (!selection) {
      return clamp(this.activeRangeIndex >= 0 ? this.activeRangeIndex : 0, 0, this.state.ranges.length - 1);
    }

    const overlappingIndex = this.state.ranges.findIndex((range) => {
      if (selection.end > selection.start) {
        return selection.start < range.end && range.start < selection.end;
      }
      return selection.start >= range.start && selection.start <= range.end;
    });
    if (overlappingIndex >= 0) {
      return overlappingIndex;
    }

    return this.state.ranges.reduce(
      (bestIndex, range, index) => {
        const distance = selection.start < range.start
          ? range.start - selection.start
          : Math.max(selection.start - range.end, 0);
        return distance < this.distanceToSelection(selection.start, this.state.ranges[bestIndex]) ? index : bestIndex;
      },
      0,
    );
  }

  private distanceToSelection(position: number, range: SuggestionRange): number {
    if (position < range.start) {
      return range.start - position;
    }
    if (position > range.end) {
      return position - range.end;
    }
    return 0;
  }

  private getActiveRange(): SuggestionRange | null {
    if (this.activeRangeIndex < 0 || this.activeRangeIndex >= this.state.ranges.length) {
      return null;
    }
    return this.state.ranges[this.activeRangeIndex] ?? null;
  }

  private setPanelOpen(open: boolean): void {
    this.panelOpen = open;
    this.panel.classList.toggle("open", open);
    this.syncPosition();
  }

  private renderActiveActions(activeRange: SuggestionRange): void {
    this.activeActions.replaceChildren();

    const replacements = activeRange.suggestion.replacement_options.slice(0, 2);
    for (const [index, replacement] of replacements.entries()) {
      const button = this.createActionButton(
        replacement,
        index === 0 ? "primary" : "secondary",
        () => {
          if (!this.actions.canApplySuggestion) {
            return;
          }
          const handled = this.actions.onAccept?.(activeRange, replacement);
          if (handled !== false) {
            this.setPanelOpen(false);
          }
        }
      );
      button.disabled = !this.actions.canApplySuggestion;
      this.activeActions.appendChild(button);
    }

    const dismissButton = this.createActionButton("Dismiss", "secondary", () => {
      const handled = this.actions.onDismiss?.(activeRange);
      if (handled !== false) {
        this.dismissRange(this.activeRangeIndex);
      }
    });
    this.activeActions.appendChild(dismissButton);
  }

  private createActionButton(
    label: string,
    variant: "primary" | "secondary",
    onClick: () => void,
  ): HTMLButtonElement {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `action-button action-button--${variant}`;
    button.textContent = label;
    button.title = label;
    button.addEventListener("click", onClick);
    return button;
  }

  private dismissRange(index: number): void {
    if (index < 0 || index >= this.state.ranges.length) {
      return;
    }

    const nextRanges = this.state.ranges.filter((_, rangeIndex) => rangeIndex !== index);
    if (nextRanges.length === 0) {
      this.hide();
      return;
    }

    this.state = {
      ...this.state,
      ranges: nextRanges,
    };
    this.activeRangeIndex = Math.min(index, nextRanges.length - 1);
    this.renderRail();
    this.renderPanel();
    if (this.target && supportsInlineMirror(this.target)) {
      this.renderInlineMirror(this.target, this.state);
    }
    this.syncPosition();
  }
}

function normalizeOverlayState(state: OverlayState): OverlayState {
  const textLength = state.text.length;
  const ranges = [...state.ranges]
    .filter((range) => range.end > range.start)
    .map((range) => ({
      ...range,
      start: clamp(range.start, 0, textLength),
      end: clamp(range.end, 0, textLength),
    }))
    .filter((range) => range.end > range.start)
    .sort((left, right) => left.start - right.start || left.end - right.end)
    .slice(0, MAX_RENDERED_RANGES);

  return {
    text: state.text,
    ranges,
  };
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

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}
