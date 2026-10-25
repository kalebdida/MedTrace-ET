import { useEffect, useRef, useState } from "react";
import { DemoRun, demoDependencies, type DemoState } from "./demo";
import { useI18n } from "./i18n";
import { en, type TranslationKey } from "./translations";
import { Icon } from "./Icon";
import { ResultCard } from "./ResultCard";
import { HistoryView } from "./HistoryPage";
const steps = ["demoStep1", "demoStep2", "demoStep3", "demoStep4", "demoStep5"] as const;
export default function DemoPage({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const run = useRef<DemoRun | undefined>(undefined);
  const [state, setState] = useState<DemoState>();
  const [adama, setAdama] = useState("");
  const [dessie, setDessie] = useState("");
  const [busy, setBusy] = useState(false);
  const [recoveryError, setRecoveryError] = useState(false);
  useEffect(() => () => run.current?.dispose(), []);
  async function next() {
    if (busy) return;
    setBusy(true);
    if (!run.current) run.current = new DemoRun(demoDependencies());
    try {
      const result = await run.current.next({ adama, dessie });
      setState({ ...result });
      if (result.step >= 3) {
        setAdama("");
        setDessie("");
      }
    } finally {
      setBusy(false);
    }
  }
  async function recover() {
    setBusy(true);
    setRecoveryError(false);
    try {
      await run.current?.recoverHistory();
      if (run.current) setState({ ...run.current.state });
    } catch {
      setRecoveryError(true);
    } finally {
      setBusy(false);
    }
  }
  function restart() {
    run.current?.dispose();
    run.current = undefined;
    setState(undefined);
    setAdama("");
    setDessie("");
    setRecoveryError(false);
  }
  return (
    <section className="page demo-page">
      <div className="page-heading">
        <span className="eyebrow">{t("demo")}</span>
        <h1>{t("demoTitle")}</h1>
        <p>{t("demoHint")}</p>
      </div>
      <div className="card">
        <div className="demo-route" aria-hidden>
          <span>ADAMA</span>
          <span>· · · → · · ·</span>
          <span>DESSIE</span>
        </div>
        {!state && (
          <>
            <label>
              {t("adamaPassword")}
              <input
                type="password"
                autoComplete="off"
                value={adama}
                onChange={(e) => setAdama(e.target.value)}
              />
            </label>
            <label>
              {t("dessiePassword")}
              <input
                type="password"
                autoComplete="off"
                value={dessie}
                onChange={(e) => setDessie(e.target.value)}
              />
            </label>
            <p className="hint">{t("memoryOnly")}</p>
          </>
        )}
        <ol className="demo-steps">
          {steps.map((key, index) => (
            <li
              key={key}
              className={(state?.step ?? 0) > index ? "done" : ""}
              aria-current={(state?.step ?? 0) === index ? "step" : undefined}
            >
              <span aria-hidden>
                {(state?.step ?? 0) > index ? <Icon name="check" size={16} /> : index + 1}
              </span>
              {t(key)}
            </li>
          ))}
        </ol>
        <div role="status">{state?.step === 5 ? t("demoDone") : busy ? t("loading") : null}</div>
        {state?.error && (
          <p className="error" role="alert">
            {t((state.error in en ? state.error : "requestFailed") as TranslationKey)}
          </p>
        )}
        {state?.error ? (
          <>
            <button className="secondary" onClick={recover} disabled={busy}>
              {t("showHistory")}
            </button>
            <button className="primary" onClick={restart} disabled={busy}>
              {t("restartDemo")}
            </button>
          </>
        ) : state?.step === 5 ? (
          <button className="primary" onClick={restart}>
            {t("restartDemo")}
          </button>
        ) : (
          <button
            className="primary"
            onClick={next}
            disabled={busy || (!state && (!adama || !dessie))}
          >
            {t(state ? "nextDemo" : "startDemo")} →
          </button>
        )}
        {recoveryError && (
          <p role="alert" className="error">
            {t("requestFailed")}
          </p>
        )}
        <button className="link" onClick={onClose}>
          {t("cancel")}
        </button>
      </div>
      {(state?.dessie ?? state?.adama) && <ResultCard result={(state?.dessie ?? state?.adama)!} />}
      {state?.history && <HistoryView history={state.history} autoMap />}
    </section>
  );
}
