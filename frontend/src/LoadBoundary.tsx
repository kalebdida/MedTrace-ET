import { Component, type ReactNode } from "react";
import { useI18n } from "./i18n";
class Boundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
export function LoadBoundary({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  return (
    <Boundary
      fallback={
        <section className="card" role="alert">
          <p>{t("networkError")}</p>
          <button className="secondary" onClick={() => window.location.reload()}>
            {t("retry")}
          </button>
        </section>
      }
    >
      {children}
    </Boundary>
  );
}
