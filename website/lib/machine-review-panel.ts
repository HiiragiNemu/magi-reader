export const MACHINE_REVIEW_PANEL_STORAGE_KEY =
  'magi-reader-machine-review-panel-v1';

const COLLAPSED_VALUE = 'collapsed';
const EXPANDED_VALUE = 'expanded';
const CHANGE_EVENT = 'magi-reader-machine-review-panel-change';
let volatileCollapsed = false;

type StorageReader = Pick<Storage, 'getItem'>;
type StorageWriter = Pick<Storage, 'setItem'>;

export const isMachineReviewPanelCollapsedValue = (
  value: string | null,
): boolean => value === COLLAPSED_VALUE;

export const readMachineReviewPanelCollapsed = (
  getStorage: () => StorageReader,
): boolean => {
  try {
    return isMachineReviewPanelCollapsedValue(
      getStorage().getItem(MACHINE_REVIEW_PANEL_STORAGE_KEY),
    );
  } catch {
    return false;
  }
};

export const writeMachineReviewPanelCollapsed = (
  getStorage: () => StorageWriter,
  collapsed: boolean,
): boolean => {
  try {
    getStorage().setItem(
      MACHINE_REVIEW_PANEL_STORAGE_KEY,
      collapsed ? COLLAPSED_VALUE : EXPANDED_VALUE,
    );
    return true;
  } catch {
    return false;
  }
};

export const getMachineReviewPanelSnapshot = (): boolean => {
  if (typeof window === 'undefined') return volatileCollapsed;
  try {
    const stored = window.localStorage.getItem(
      MACHINE_REVIEW_PANEL_STORAGE_KEY,
    );
    return stored === null
      ? volatileCollapsed
      : isMachineReviewPanelCollapsedValue(stored);
  } catch {
    return volatileCollapsed;
  }
};

export const getMachineReviewPanelServerSnapshot = (): boolean => false;

export const subscribeMachineReviewPanel = (
  onStoreChange: () => void,
): (() => void) => {
  if (typeof window === 'undefined') return () => {};

  const onStorage = (event: StorageEvent) => {
    if (event.key === MACHINE_REVIEW_PANEL_STORAGE_KEY) {
      volatileCollapsed = isMachineReviewPanelCollapsedValue(event.newValue);
      onStoreChange();
    }
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(CHANGE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(CHANGE_EVENT, onStoreChange);
  };
};

export const setMachineReviewPanelCollapsedPreference = (
  collapsed: boolean,
): void => {
  volatileCollapsed = collapsed;
  if (typeof window === 'undefined') return;
  writeMachineReviewPanelCollapsed(() => window.localStorage, collapsed);
  window.dispatchEvent(new Event(CHANGE_EVENT));
};
