import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

interface OnlineContextValue {
  online: boolean;
}

const OnlineContext = createContext<OnlineContextValue>({ online: true });

export function OnlineProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  const value = useMemo(() => ({ online }), [online]);
  return <OnlineContext.Provider value={value}>{children}</OnlineContext.Provider>;
}

export function useOnline(): OnlineContextValue {
  return useContext(OnlineContext);
}