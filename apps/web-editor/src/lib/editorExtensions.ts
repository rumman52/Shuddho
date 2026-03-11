import { Mark, mergeAttributes } from "@tiptap/core";

export const IssueMark = Mark.create({
  name: "issue",
  inclusive: false,
  excludes: "",
  addAttributes() {
    return {
      suggestionId: {
        default: null,
        parseHTML: (element: HTMLElement) => element.getAttribute("data-issue-id")
      },
      severity: {
        default: "medium"
      }
    };
  },
  parseHTML() {
    return [{ tag: "span[data-issue-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-issue-id": HTMLAttributes.suggestionId,
        class: `issue-mark issue-mark--${HTMLAttributes.severity}`
      }),
      0
    ];
  }
});

