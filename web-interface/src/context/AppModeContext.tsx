import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

const STORAGE_KEY = "archivespace-advanced-mode";

interface AppModeContextValue {
  advancedMode: boolean;
  setAdvancedMode: (value: boolean) => void;
  toggleAdvancedMode: () => void;
}

const AppModeContext = createContext<AppModeContextValue | null>(null);

export function AppModeProvider({ children }: { children: ReactNode }) {
  const [advancedMode, setAdvancedModeState] = useState(() => {
    return window.localStorage.getItem(STORAGE_KEY) === "true";
  });

  const setAdvancedMode = useCallback((value: boolean) => {
    setAdvancedModeState(value);
    window.localStorage.setItem(STORAGE_KEY, String(value));
  }, []);

  const toggleAdvancedMode = useCallback(() => {
    setAdvancedMode(!advancedMode);
  }, [advancedMode, setAdvancedMode]);

  const value = useMemo(
    () => ({ advancedMode, setAdvancedMode, toggleAdvancedMode }),
    [advancedMode, setAdvancedMode, toggleAdvancedMode],
  );

  return <AppModeContext.Provider value={value}>{children}</AppModeContext.Provider>;
}

export function useAppMode(): AppModeContextValue {
  const ctx = useContext(AppModeContext);
  if (!ctx) throw new Error("useAppMode must be used within AppModeProvider");
  return ctx;
}