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

type FloatingPoint = {
  x: number;
  y: number;
};

type DraggableReaderWidgetProps = {
  storageKey: string;
  defaultDock: 'top-right' | 'bottom-right';
  ariaLabel: string;
  dragHandleLabel: string;
  className?: string;
  children: ReactNode;
};

const VIEWPORT_MARGIN_PX = 8;

const parseStoredPoint = (value: string | null): FloatingPoint | null => {
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null;
    }
    const record = parsed as Record<string, unknown>;
    if (
      typeof record.x !== 'number'
      || typeof record.y !== 'number'
      || !Number.isFinite(record.x)
      || !Number.isFinite(record.y)
    ) {
      return null;
    }
    return { x: record.x, y: record.y };
  } catch {
    return null;
  }
};

export default function DraggableReaderWidget({
  storageKey,
  defaultDock,
  ariaLabel,
  dragHandleLabel,
  className = '',
  children,
}: DraggableReaderWidgetProps) {
  const widgetRef = useRef<HTMLDivElement>(null);
  const positionRef = useRef<FloatingPoint | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    offsetX: number;
    offsetY: number;
  } | null>(null);
  const [position, setPositionState] = useState<FloatingPoint | null>(null);
  const [dragging, setDragging] = useState(false);

  const setPosition = useCallback((next: FloatingPoint | null) => {
    positionRef.current = next;
    setPositionState(next);
  }, []);

  const clampPoint = useCallback((point: FloatingPoint): FloatingPoint => {
    const rect = widgetRef.current?.getBoundingClientRect();
    const width = rect?.width ?? 0;
    const height = rect?.height ?? 0;
    return {
      x: Math.min(
        Math.max(VIEWPORT_MARGIN_PX, point.x),
        Math.max(VIEWPORT_MARGIN_PX, window.innerWidth - width - VIEWPORT_MARGIN_PX),
      ),
      y: Math.min(
        Math.max(VIEWPORT_MARGIN_PX, point.y),
        Math.max(VIEWPORT_MARGIN_PX, window.innerHeight - height - VIEWPORT_MARGIN_PX),
      ),
    };
  }, []);

  const persistPoint = useCallback((point: FloatingPoint | null) => {
    try {
      if (point) {
        window.localStorage.setItem(storageKey, JSON.stringify(point));
      } else {
        window.localStorage.removeItem(storageKey);
      }
    } catch {
      // Dragging remains available for the current visit when storage is blocked.
    }
  }, [storageKey]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      let restored: FloatingPoint | null = null;
      try {
        restored = parseStoredPoint(window.localStorage.getItem(storageKey));
      } catch {
        restored = null;
      }
      if (restored) setPosition(clampPoint(restored));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [clampPoint, setPosition, storageKey]);

  useEffect(() => {
    const keepInsideViewport = () => {
      const current = positionRef.current;
      if (!current) return;
      const next = clampPoint(current);
      if (next.x !== current.x || next.y !== current.y) {
        setPosition(next);
        persistPoint(next);
      }
    };

    window.addEventListener('resize', keepInsideViewport);
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(keepInsideViewport);
    if (widgetRef.current) observer?.observe(widgetRef.current);
    return () => {
      window.removeEventListener('resize', keepInsideViewport);
      observer?.disconnect();
    };
  }, [clampPoint, persistPoint, setPosition]);

  const beginDrag = useCallback((
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    const rect = widgetRef.current?.getBoundingClientRect();
    if (!rect) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    setDragging(true);
  }, []);

  const moveDrag = useCallback((
    event: ReactPointerEvent<HTMLButtonElement>,
  ) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    setPosition(clampPoint({
      x: event.clientX - drag.offsetX,
      y: event.clientY - drag.offsetY,
    }));
  }, [clampPoint, setPosition]);

  const finishDrag = useCallback((
    event: ReactPointerEvent<HTMLButtonElement>,
    persist: boolean,
  ) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // The browser may already have released pointer capture.
    }
    if (persist) persistPoint(positionRef.current);
  }, [persistPoint]);

  const resetPosition = useCallback(() => {
    dragRef.current = null;
    setDragging(false);
    setPosition(null);
    persistPoint(null);
  }, [persistPoint, setPosition]);

  const style = position
    ? ({
        left: `${position.x}px`,
        top: `${position.y}px`,
        right: 'auto',
        bottom: 'auto',
      } satisfies CSSProperties)
    : undefined;

  return (
    <div
      ref={widgetRef}
      data-default-dock={defaultDock}
      data-reader-floating-widget="true"
      className={`magi-reader-floating-widget ${dragging ? 'is-dragging' : ''} ${className}`}
      style={style}
      role="group"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        className="magi-reader-floating-grip"
        aria-label={dragHandleLabel}
        title={`${dragHandleLabel}；双击恢复默认位置`}
        onPointerDown={beginDrag}
        onPointerMove={moveDrag}
        onPointerUp={event => finishDrag(event, true)}
        onPointerCancel={event => finishDrag(event, false)}
        onDoubleClick={resetPosition}
      >
        <span aria-hidden="true">⋮⋮</span>
      </button>
      {children}
    </div>
  );
}
