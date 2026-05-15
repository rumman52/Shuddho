import { create } from 'zustand';
import type { Suggestion } from '@shuddho/shared';

type Status = 'idle' | 'checking' | 'synced' | 'offline';
interface EditorState {
  documentId: string; revision: number; text: string; suggestions: Suggestion[]; rejected: Set<string>; status: Status;
  setText: (text: string) => void; setSuggestions: (suggestions: Suggestion[], responseRevision?: number) => void;
  accept: (suggestion: Suggestion) => void; reject: (suggestion: Suggestion) => void; setStatus: (status: Status) => void;
}
const starter = 'আমি  আমি ভাত খাই ।বাংলা ভাষা সুন্দর';
const start = (s: Suggestion) => s.span.utf16StartIndex ?? s.span.startIndex;
const end = (s: Suggestion) => s.span.utf16EndIndex ?? s.span.endIndex;
export const useEditorStore = create<EditorState>((set) => ({
  documentId: 'demo-document', revision: 0, text: starter, suggestions: [], rejected: new Set<string>(), status: 'idle',
  setText: (text) => set((state) => ({ text, revision: state.revision + 1 })),
  setSuggestions: (suggestions, responseRevision) => set((state) => responseRevision !== undefined && responseRevision !== state.revision ? state : { suggestions: suggestions.filter((item) => !state.rejected.has(item.suppressionKey) && !state.rejected.has(item.id)) }),
  accept: (suggestion) => set((state) => {
    const s = start(suggestion), e = end(suggestion);
    if (state.text.slice(s, e) !== suggestion.originalText) return { suggestions: state.suggestions.filter((item) => item.id !== suggestion.id) };
    return { text: state.text.slice(0, s) + suggestion.suggestedText + state.text.slice(e), revision: state.revision + 1, suggestions: state.suggestions.filter((item) => item.id !== suggestion.id) };
  }),
  reject: (suggestion) => set((state) => { const rejected = new Set(state.rejected); rejected.add(suggestion.suppressionKey); rejected.add(suggestion.id); return { rejected, suggestions: state.suggestions.filter((item) => item.id !== suggestion.id) }; }),
  setStatus: (status) => set({ status }),
}));
