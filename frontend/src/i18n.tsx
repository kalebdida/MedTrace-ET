import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { en, am, type TranslationKey } from "./translations";
export type Language = "en" | "am";
export const LanguageContext = createContext({
  language: "en" as Language,
  setLanguage: (_language: Language) => {},
  t: (key: TranslationKey): string => en[key],
});
export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() =>
    localStorage.getItem("medtrace-language") === "am" ? "am" : "en",
  );
  useEffect(() => {
    document.documentElement.lang = language;
    localStorage.setItem("medtrace-language", language);
  }, [language]);
  return (
    <LanguageContext.Provider
      value={{ language, setLanguage, t: (key) => (language === "am" ? am : en)[key] }}
    >
      {children}
    </LanguageContext.Provider>
  );
}
export const useI18n = () => useContext(LanguageContext);
export function LanguageSwitch() {
  const { language, setLanguage, t } = useI18n();
  return (
    <select
      className="language"
      aria-label={t("language")}
      value={language}
      onChange={(e) => setLanguage(e.target.value as Language)}
    >
      <option value="en">English</option>
      <option value="am">አማርኛ</option>
    </select>
  );
}
