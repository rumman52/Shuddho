const iconPaths: Record<string, string[]> = {
  home: ["M3 10.5 12 3l9 7.5", "M5 9v11h14V9", "M9 20v-6h6v6"],
  activity: ["M3 12h4l3-8 4 16 3-8h4"],
  target: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z", "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"],
  calendar: ["M4 5h16v16H4z", "M8 3v4", "M16 3v4", "M4 10h16"],
  globe: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M3 12h18", "M12 3a15 15 0 0 1 0 18", "M12 3a15 15 0 0 0 0 18"],
  "file-text": ["M6 3h8l4 4v14H6z", "M14 3v5h4", "M9 12h6", "M9 16h6"],
  folder: ["M3 6h7l2 2h9v11H3z", "M3 9h18"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z", "m9 12 2 2 4-4"],
  terminal: ["M4 5h16v14H4z", "m8 9 3 3-3 3", "M13 15h3"],
  wallet: ["M4 6h16v14H4z", "M6 6l2-3h10", "M15 12h5", "M16.5 12h.01"],
  handshake: ["M3 12h5l2-2 4 4 3-2 4 2", "m3 12 3 5 4-2", "m13 14 3 3 4-2"],
};
export default function NavigationIcon({ name }: { name: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {(iconPaths[name] ?? []).map((path, index) => <path d={path} key={index} />)}
  </svg>;
}
