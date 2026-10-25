export type IconName =
  | "scan"
  | "history"
  | "demo"
  | "tools"
  | "arrow"
  | "check"
  | "cross"
  | "warn"
  | "moon"
  | "sun"
  | "cube";

export function Icon({ name, size = 22 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, string> = {
    scan: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5 M8 8h8v8H8z",
    history: "M4 5l5-2 6 3 5-2v15l-5 2-6-3-5 2z M9 3v15 M15 6v15",
    demo: "M4 7h15l-4-4 M20 17H5l4 4",
    tools: "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z",
    arrow: "M4 12h16 M14 6l6 6-6 6",
    check: "M5 12.5l4.5 4.5L19 7.5",
    cross: "M6.5 6.5l11 11 M17.5 6.5l-11 11",
    warn: "M12 7.5v5.5 M12 16.5h.01",
    moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    sun: "M12 3v2 M12 19v2 M4.2 4.2l1.4 1.4 M18.4 18.4l1.4 1.4 M3 12h2 M19 12h2 M4.2 19.8l1.4-1.4 M18.4 5.6l1.4-1.4 M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
    cube: "M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z M12 12l8-4.5 M12 12v9 M12 12L4 7.5",
  };
  const strokeWidth = name === "check" || name === "cross" || name === "warn" ? "2.4" : "1.75";
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
