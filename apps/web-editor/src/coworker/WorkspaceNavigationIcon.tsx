const iconPaths: Record<string, string[]> = {
  chat: ["M4 4h16v12H9l-5 4V4Z"],
  layout: ["M3 4h18v16H3z", "M3 9h18", "M9 9v11"],
  search: ["M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Z", "m16 16 5 5"],
  grid: ["M3 3h6v6H3z", "M15 3h6v6h-6z", "M3 15h6v6H3z", "M15 15h6v6h-6z"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  sliders: ["M7 3v18", "M17 3v18", "M3 8h8", "M13 16h8"],
  settings: ["M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z", "M19.4 13.5a7.6 7.6 0 0 0 0-3l1.5-1.1-1.5-2.6-1.8.7a7.7 7.7 0 0 0-2.6-1.5L14.7 4h-3.4l-.3 2a7.7 7.7 0 0 0-2.6 1.5l-1.8-.7-1.5 2.6 1.5 1.1a7.6 7.6 0 0 0 0 3l-1.5 1.1 1.5 2.6 1.8-.7a7.7 7.7 0 0 0 2.6 1.5l.3 2h3.4l.3-2a7.7 7.7 0 0 0 2.6-1.5l1.8.7 1.5-2.6-1.5-1.1Z"],
  "log-out": ["M10 17l5-5-5-5", "M15 12H3", "M12 3h7v18h-7"],
  plus: ["M12 4v16", "M4 12h16"],
  arrow: ["M12 20V4", "m5 11 7-7 7 7"],
  home: ["M3 10.5 12 3l9 7.5", "M5 9v11h14V9", "M9 20v-6h6v6"],
  activity: ["M3 12h4l3-8 4 16 3-8h4"],
  target: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z", "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"],
  calendar: ["M4 5h16v16H4z", "M8 3v4", "M16 3v4", "M4 10h16"],
  globe: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M3 12h18", "M12 3a15 15 0 0 1 0 18", "M12 3a15 15 0 0 0 0 18"],
  "file-text": ["M6 3h8l4 4v14H6z", "M14 3v5h4", "M9 12h6", "M9 16h6"],
  folder: ["M3 6h7l2 2h9v11H3z", "M3 9h18"],
  "arrow-left": ["M19 12H5", "m12 19-7-7 7-7"],
  "arrow-right": ["M5 12h14", "m12 5 7 7-7 7"],
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
