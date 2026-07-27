export const PROOFREADING_RECEIPTS_KEY = 'magi-reader-proofreading-receipts-v1';

export type StoredProofreadingReceipt = {
  id: string;
  receipt: string;
  storyId: string;
  nickname: string;
  submittedAt: string;
};

export const saveProofreadingReceipt = (
  receipt: StoredProofreadingReceipt,
): void => {
  try {
    const raw = localStorage.getItem(PROOFREADING_RECEIPTS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    const current = Array.isArray(parsed)
      ? parsed.filter((item) => item && typeof item === 'object')
      : [];
    const next = [
      receipt,
      ...current.filter((item) =>
        (item as Record<string, unknown>).id !== receipt.id,
      ),
    ].slice(0, 100);
    localStorage.setItem(PROOFREADING_RECEIPTS_KEY, JSON.stringify(next));
  } catch {
    // Submissions still succeed when browser storage is disabled.
  }
};
