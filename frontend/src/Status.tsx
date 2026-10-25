import { useEffect, useState } from "react";
import { api } from "./api";
import { useI18n } from "./i18n";
export function ServerStatus() {
  const { t } = useI18n();
  const [state, setState] = useState<"waking" | "ready" | "offline" | "unavailable">("waking");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const ping = () => {
      if (!navigator.onLine) {
        setState("offline");
        return;
      }
      setState("waking");
      api<{ status: string }>("/health", { signal: controller.signal })
        .then((r) => {
          if (active) setState(r.status === "ok" ? "ready" : "unavailable");
        })
        .catch(() => {
          if (active) setState(navigator.onLine ? "unavailable" : "offline");
        });
    };
    const offline = () => setState("offline");
    ping();
    window.addEventListener("online", ping);
    window.addEventListener("offline", offline);
    return () => {
      active = false;
      controller.abort();
      window.removeEventListener("online", ping);
      window.removeEventListener("offline", offline);
    };
  }, [retry]);
  return (
    <div className="server-status">
      <span className={`status-chip ${state}`} role="status">
        <span className="status-dot" />
        {t(state)}
      </span>
      {state === "unavailable" && (
        <button className="link" onClick={() => setRetry((n) => n + 1)}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}
