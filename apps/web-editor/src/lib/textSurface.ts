import type { Editor } from "@tiptap/react";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";

export interface TextSegment {
  start: number;
  end: number;
  from: number;
  to: number;
}

export interface EditorTextSurface {
  text: string;
  segments: TextSegment[];
}

export function getEditorTextSurface(editor: Editor): EditorTextSurface {
  const segments: TextSegment[] = [];
  const parts: string[] = [];
  let textOffset = 0;

  editor.state.doc.forEach((node, offset, index) => {
    textOffset = collectNodeText(node, offset, textOffset, parts, segments);
    if (index < editor.state.doc.childCount - 1) {
      parts.push("\n");
      textOffset += 1;
    }
  });

  return {
    text: parts.join(""),
    segments,
  };
}

function collectNodeText(
  node: ProseMirrorNode,
  nodePos: number,
  textOffset: number,
  parts: string[],
  segments: TextSegment[]
): number {
  let currentOffset = textOffset;

  node.forEach((child, childOffset, index) => {
    const childPos = nodePos + childOffset + 1;

    if (child.isText && child.text) {
      parts.push(child.text);
      segments.push({
        start: currentOffset,
        end: currentOffset + child.text.length,
        from: childPos,
        to: childPos + child.text.length,
      });
      currentOffset += child.text.length;
      return;
    }

    if (child.type.name === "hardBreak") {
      parts.push("\n");
      currentOffset += 1;
      return;
    }

    const beforeChild = currentOffset;
    currentOffset = collectNodeText(child, childPos, currentOffset, parts, segments);
    if (child.isBlock && index < node.childCount - 1 && currentOffset > beforeChild) {
      parts.push("\n");
      currentOffset += 1;
    }
  });

  return currentOffset;
}
