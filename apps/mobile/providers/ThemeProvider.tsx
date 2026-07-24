import React, { createContext, useContext, useMemo } from "react";
import { theme, Theme } from "../theme";

interface ThemeContextValue {
  theme: Theme;
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export interface ThemeProviderProps {
  children: React.ReactNode;
  isDark?: boolean;
}

export function ThemeProvider({ children, isDark = false }: ThemeProviderProps) {
  const value = useMemo(
    () => ({
      theme,
      isDark,
    }),
    [isDark]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeContext(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useThemeContext must be used within a ThemeProvider");
  }
  return context;
}
