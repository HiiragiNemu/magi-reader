export const SIDEBAR_WIDTH_STORAGE_KEY = 'magi-reader-sidebar-width-v1';
export const SIDEBAR_WIDTH_DEFAULT = 288;
export const SIDEBAR_WIDTH_MIN = 240;
export const SIDEBAR_WIDTH_MAX = 560;
export const SIDEBAR_WIDTH_STEP = 16;

export const clampSidebarWidth = (value: number): number => {
  if (!Number.isFinite(value)) return SIDEBAR_WIDTH_DEFAULT;
  return Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, Math.round(value)));
};

export const parseStoredSidebarWidth = (raw: string | null): number => {
  if (raw === null || raw.trim() === '') return SIDEBAR_WIDTH_DEFAULT;
  return clampSidebarWidth(Number(raw));
};
