'use client';

import { useEffect, useRef } from 'react';

type TurnstileApi = {
  render(
    container: string | HTMLElement,
    options: {
      sitekey: string;
      action?: string;
      theme?: 'light' | 'dark' | 'auto';
      size?: 'normal' | 'compact' | 'flexible';
      callback?: (token: string) => void;
      'expired-callback'?: () => void;
      'error-callback'?: () => void;
    },
  ): string;
  remove(widgetId: string): void;
  reset(widgetId?: string): void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
    __magiTurnstilePromise?: Promise<TurnstileApi>;
  }
}

const SCRIPT_URL =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

const loadTurnstile = (): Promise<TurnstileApi> => {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (window.__magiTurnstilePromise) return window.__magiTurnstilePromise;

  window.__magiTurnstilePromise = new Promise<TurnstileApi>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${SCRIPT_URL}"]`,
    );
    const script = existing ?? document.createElement('script');
    const finish = () => {
      if (window.turnstile) resolve(window.turnstile);
      else reject(new Error('Turnstile API did not initialize'));
    };
    script.addEventListener('load', finish, { once: true });
    script.addEventListener(
      'error',
      () => reject(new Error('Turnstile script failed to load')),
      { once: true },
    );
    if (!existing) {
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  });
  return window.__magiTurnstilePromise;
};

type TurnstileWidgetProps = {
  siteKey: string;
  theme: string;
  resetKey: number;
  onToken: (token: string) => void;
  onError?: (message: string) => void;
};

export default function TurnstileWidget({
  siteKey,
  theme,
  resetKey,
  onToken,
  onError,
}: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    onToken('');
    void loadTurnstile()
      .then((turnstile) => {
        if (!active || !containerRef.current) return;
        if (widgetIdRef.current) turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action: 'proofreading-submit',
          theme: theme === 'dark' ? 'dark' : 'light',
          size: 'flexible',
          callback: (token) => {
            if (active) onToken(token);
          },
          'expired-callback': () => {
            if (active) onToken('');
          },
          'error-callback': () => {
            if (!active) return;
            onToken('');
            onError?.('人机验证加载失败，请刷新后重试。');
          },
        });
      })
      .catch(() => {
        if (active) onError?.('无法连接人机验证服务。');
      });
    return () => {
      active = false;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
      widgetIdRef.current = null;
    };
  }, [onError, onToken, resetKey, siteKey, theme]);

  return <div ref={containerRef} className="min-h-[65px] w-full" />;
}
