"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import { X } from 'lucide-react';

type FloatingWindowProps = {
  isOpen: boolean;
  onClose: () => void;
  theme: string;
  title: string;
  titleId: string;
  systemLabel: string;
  children: ReactNode;
  footer?: ReactNode;
  initialOffset?: { x: number; y: number };
  className?: string;
  bodyClassName?: string;
};

const constrainOffset = (x: number, y: number, width: number, height: number) => ({
  x: Math.max(8, Math.min(x, Math.max(8, window.innerWidth - width - 8))),
  y: Math.max(8, Math.min(y, Math.max(8, window.innerHeight - height - 8))),
});

/**
 * A deliberately modeless child window.  It never renders a full-page backdrop,
 * never traps focus and therefore leaves the Reader usable while one or more
 * tool windows remain open.
 */
export default function FloatingWindow({
  isOpen,
  onClose,
  theme,
  title,
  titleId,
  systemLabel,
  children,
  footer,
  initialOffset = { x: 48, y: 36 },
  className = '',
  bodyClassName = '',
}: FloatingWindowProps) {
  const windowRef = useRef<HTMLElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const [offset, setOffset] = useState(initialOffset);
  const [zIndex, setZIndex] = useState(70);

  useEffect(() => () => cleanupRef.current?.(), []);

  const raise = useCallback(() => {
    const next = Number(document.documentElement.dataset.magiWindowZ || '70') + 1;
    document.documentElement.dataset.magiWindowZ = String(next);
    setZIndex(next);
  }, []);

  const startDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest('button, a, input')) return;
    const node = windowRef.current;
    if (!node) return;
    event.preventDefault();
    raise();
    cleanupRef.current?.();
    const rect = node.getBoundingClientRect();
    const origin = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
    const move = (moveEvent: PointerEvent) => {
      const next = constrainOffset(
        origin.left + moveEvent.clientX - origin.x,
        origin.top + moveEvent.clientY - origin.y,
        rect.width,
        rect.height,
      );
      setOffset(next);
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      cleanupRef.current = null;
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop, { once: true });
    window.addEventListener('pointercancel', stop, { once: true });
    cleanupRef.current = stop;
  }, [raise]);

  if (!isOpen) return null;

  const style = {
    '--magi-window-x': `${offset.x}px`,
    '--magi-window-y': `${offset.y}px`,
    zIndex,
  } as CSSProperties;
  const palette = theme === 'paper'
    ? 'magi-floating-window-paper'
    : theme === 'light'
      ? 'magi-floating-window-light'
      : `magi-floating-window-${theme}`;

  return (
    <section
      ref={windowRef}
      role="dialog"
      aria-labelledby={titleId}
      tabIndex={-1}
      data-modeless="true"
      data-theme={theme}
      className={`magi-floating-window ${palette} ${className}`}
      style={style}
      onPointerDown={raise}
    >
      <div className="magi-floating-window-titlebar" onPointerDown={startDrag}>
        <div className="min-w-0">
          <div className="magi-floating-window-system-label">{systemLabel}</div>
          <h2 id={titleId} className="magi-floating-window-title">{title}</h2>
        </div>
        <button
          type="button"
          aria-label={`关闭${title}`}
          title="关闭"
          onClick={onClose}
          className="magi-retro-window-close"
        >
          <X aria-hidden="true" size={18} strokeWidth={2.4} />
        </button>
      </div>
      <div className={`magi-floating-window-body ${bodyClassName}`}>{children}</div>
      {footer && <div className="magi-floating-window-footer">{footer}</div>}
    </section>
  );
}
