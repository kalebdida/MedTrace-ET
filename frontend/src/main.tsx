import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { LanguageProvider } from "./i18n";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LanguageProvider>
      <App />
    </LanguageProvider>
  </StrictMode>,
);

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  const registerSw = () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  };
  if (document.readyState === "complete") {
    registerSw();
  } else {
    window.addEventListener("load", registerSw);
  }
}
