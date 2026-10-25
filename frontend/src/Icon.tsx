export function Icon({ name }: { name: "scan" | "history" | "demo" | "tools" | "arrow" }) {
  const paths = {
    scan: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5 M8 8h8v8H8z",
    history: "M4 5l5-2 6 3 5-2v15l-5 2-6-3-5 2z M9 3v15 M15 6v15",
    demo: "M4 7h15l-4-4 M20 17H5l4 4",
    tools: "M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z",
    arrow: "M4 12h16 M14 6l6 6-6 6",
  };
  return (
    <svg
      aria-hidden="true"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
