"use client";

import { createContext, useContext, useEffect, useState } from "react";

// 新增 'green'
type Theme = 'light' | 'dark' | 'paper' | 'green';

interface GlobalState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  lastCategory: string;
  setLastCategory: (c: string) => void;
}

const GlobalContext = createContext<GlobalState | undefined>(undefined);

export function GlobalProvider({ children }: { children: React.ReactNode }) {
  // 默认改为 'paper' (你要求的暖黄色)
  const [theme, setThemeState] = useState<Theme>('paper');
  const [lastCategory, setLastCategory] = useState('main_story');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem('magi_theme') as Theme;
    const savedCat = localStorage.getItem('magi_cat');
    if (savedTheme) setThemeState(savedTheme);
    if (savedCat) setLastCategory(savedCat);
    setMounted(true);
  }, []);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem('magi_theme', t);
    // 处理 CSS 类
    const root = document.documentElement;
    root.classList.remove('dark', 'theme-paper', 'theme-green');
    if (t === 'dark') root.classList.add('dark');
    if (t === 'paper') root.classList.add('theme-paper');
    if (t === 'green') root.classList.add('theme-green');
  };

  const setLastCategoryWrapper = (c: string) => {
    setLastCategory(c);
    localStorage.setItem('magi_cat', c);
  };

  return (
    <GlobalContext.Provider value={{ theme, setTheme, lastCategory, setLastCategory: setLastCategoryWrapper }}>
      {/* 应用噪点背景 */}
      <div className={`min-h-screen ${theme === 'paper' ? 'bg-noise theme-paper' : theme === 'green' ? 'theme-green' : theme === 'dark' ? 'dark bg-gray-900 text-gray-100' : 'bg-white text-gray-900'}`}>
        {children}
      </div>
    </GlobalContext.Provider>
  );
}

export const useGlobal = () => {
  const context = useContext(GlobalContext);
  if (!context) throw new Error("useGlobal must be used within GlobalProvider");
  return context;
};