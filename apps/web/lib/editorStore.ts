import { create } from 'zustand';
import type { Suggestion } from '@shuddho/shared';

type Status = 'idle' | 'checking' | 'synced' | 'offline';
interface EditorState {
  documentId: string;
  revision: number;
  text: string;
  suggestions: Suggestion[];
  rejected: Set<string>;
  status: Status;
  setText: (text: string) => void;
  setSuggestions: (suggestions: Suggestion[]) => void;
  accept: (suggestion: Suggestion) => void;
  reject: (suggestion: Suggestion) => void;
  setStatus: (status: Status) => void;
}

const starter = 'I has teh first draft.  This is terrible due to the fact that it was created in order to test recieve suggestions.';

export const useEditorStore = create<EditorState>((set) => ({
  documentId: 'demo-document',
  revision: 0,
  text: starter,
  suggestions: [],
  rejected: new Set<string>(),
  status: 'idle',
  setText: (text) => set((state) => ({ text, revision: state.revision + 1 })),
  setSuggestions: (suggestions) => set((state) => ({ suggestions: suggestions.filter((item) => !state.rejected.has(item.id)) })),
  accept: (suggestion) => set((state) => {
    const nextText = state.text.slice(0, suggestion.startIndex) + suggestion.suggestedText + state.text.slice(suggestion.endIndex);
    return { text: nextText, revision: state.revision + 1, suggestions: state.suggestions.filter((item) => item.id !== suggestion.id) };
  }),
  reject: (suggestion) => set((state) => {
    const rejected = new Set(state.rejected);
    rejected.add(suggestion.id);
    return { rejected, suggestions: state.suggestions.filter((item) => item.id !== suggestion.id) };
  }),
  setStatus: (status) => set({ status }),
}));
