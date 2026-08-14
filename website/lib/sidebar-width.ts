export const SIDEBAR_WIDTH_STORAGE_KEY = 'magi-reader-sidebar-width-v1';
export const SIDEBAR_WIDTH_DEFAULT = 288;
export const SIDEBAR_WIDTH_MIN = 240;
export const SIDEBAR_WIDTH_MAX = 560;
export const SIDEBAR_WIDTH_STEP = 16;

export const HOME_SIDEBAR_WIDTH_STORAGE_KEY = 'magi-reader-home-sidebar-width-v1';
export const HOME_SIDEBAR_WIDTH_DEFAULT = 256;
export const HOME_SIDEBAR_WIDTH_MIN = 208;
export const HOME_SIDEBAR_WIDTH_MAX = 480;
export const HOME_SIDEBAR_WIDTH_STEP = 16;

const clampWidth = (
  value: number,
  minimum: number,
  maximum: number,
  fallback: number,
): number => {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(value)));
};

export const clampSidebarWidth = (value: number): number => {
  return clampWidth(
    value,
    SIDEBAR_WIDTH_MIN,
    SIDEBAR_WIDTH_MAX,
    SIDEBAR_WIDTH_DEFAULT,
  );
};

export const parseStoredSidebarWidth = (raw: string | null): number => {
  if (raw === null || raw.trim() === '') return SIDEBAR_WIDTH_DEFAULT;
  return clampSidebarWidth(Number(raw));
};

export const clampHomeSidebarWidth = (value: number): number => {
  return clampWidth(
    value,
    HOME_SIDEBAR_WIDTH_MIN,
    HOME_SIDEBAR_WIDTH_MAX,
    HOME_SIDEBAR_WIDTH_DEFAULT,
  );
};

export const parseStoredHomeSidebarWidth = (raw: string | null): number => {
  if (raw === null || raw.trim() === '') return HOME_SIDEBAR_WIDTH_DEFAULT;
  return clampHomeSidebarWidth(Number(raw));
};
