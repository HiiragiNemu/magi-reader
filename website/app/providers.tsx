"use client";

import { createContext, useContext, useEffect, useSyncExternalStore } from "react";

import { initializeExedraFonts } from "@/lib/exedra-fonts";
import { initializeReaderFonts } from "@/lib/reader-fonts";

export type Theme = 'light' | 'dark' | 'paper' | 'green';

interface GlobalState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  lastCategory: string;
  setLastCategory: (c: string) => void;
}

const GlobalContext = createContext<GlobalState | undefined>(undefined);

const THEME_KEY = 'magi_theme';
const CATEGORY_KEY = 'magi_cat';
const THEME_EVENT = 'magi-reader-theme-change';
const CATEGORY_EVENT = 'magi-reader-category-change';
const VALID_THEMES = new Set<Theme>(['light', 'dark', 'paper', 'green']);
let volatileTheme: Theme = 'paper';
let volatileCategory = 'main_story';

const subscribeToSetting = (
  storageKey: string,
  eventName: string,
  callback: () => void,
): (() => void) => {
  const onStorage = (event: StorageEvent) => {
    if (event.key === storageKey) callback();
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(eventName, callback);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(eventName, callback);
  };
};

const readTheme = (): Theme => {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored && VALID_THEMES.has(stored as Theme)) return stored as Theme;
  } catch {
    // The in-memory value still keeps the interface usable when storage is blocked.
  }
  return volatileTheme;
};

const readCategory = (): string => {
  try {
    return localStorage.getItem(CATEGORY_KEY)?.trim() || volatileCategory;
  } catch {
    return volatileCategory;
  }
};

const subscribeTheme = (callback: () => void) =>
  subscribeToSetting(THEME_KEY, THEME_EVENT, callback);
const subscribeCategory = (callback: () => void) =>
  subscribeToSetting(CATEGORY_KEY, CATEGORY_EVENT, callback);
const serverTheme = (): Theme => 'paper';
const serverCategory = (): string => 'main_story';

export function GlobalProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(
    subscribeTheme,
    readTheme,
    serverTheme,
  );
  const lastCategory = useSyncExternalStore(
    subscribeCategory,
    readCategory,
    serverCategory,
  );

  const setTheme = (t: Theme) => {
    if (!VALID_THEMES.has(t)) return;
    volatileTheme = t;
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch {
      // Fall back to the in-memory value above.
    }
    window.dispatchEvent(new Event(THEME_EVENT));
  };

  const setLastCategoryWrapper = (c: string) => {
    const category = c.trim() || 'main_story';
    volatileCategory = category;
    try {
      localStorage.setItem(CATEGORY_KEY, category);
    } catch {
      // Fall back to the in-memory value above.
    }
    window.dispatchEvent(new Event(CATEGORY_EVENT));
  };

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  useEffect(() => {
    void initializeReaderFonts();
    void initializeExedraFonts();
  }, []);

  return (
    <GlobalContext.Provider value={{ theme, setTheme, lastCategory, setLastCategory: setLastCategoryWrapper }}>
      
      {/* 1. 背景层 */}
      <div className="magi-background" data-bg-theme={theme} />

      {/* 气球效果 */}
      <div className="magi-balloon-rain" />

      {/* 2. 内容层 */}
      <div className={`magi-site-font-scope min-h-screen transition-colors duration-300 relative z-0 bg-transparent
        ${theme === 'dark' ? 'text-gray-200' : ''}
        ${theme === 'light' ? 'text-gray-900' : ''}
        ${theme === 'paper' ? 'text-[#4a3b2a]' : ''}
        ${theme === 'green' ? 'text-[#1b5e20]' : ''}
      `}>
        {children}
      </div>

      {/* 3. 纹理层 */}
      <div className={`magi-texture ${theme === 'dark' ? 'magi-texture-dark' : 'magi-texture-light'}`} />
      
    </GlobalContext.Provider>
  );
}

export const useGlobal = () => {
  const context = useContext(GlobalContext);
  if (!context) throw new Error("useGlobal must be used within GlobalProvider");
  return context;
};
