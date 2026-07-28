const SAFE_STORY_ID_RE = /^[A-Za-z0-9_.:-]+$/;
const MAX_STORY_IDS = 100_000;

export const createKnownStoryIds = (value: unknown): ReadonlySet<string> => {
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    value.length > MAX_STORY_IDS
  ) {
    throw new Error('剧情编号清单格式或条目数无效');
  }

  const known = new Set<string>();
  const folded = new Set<string>();
  for (const item of value) {
    if (
      typeof item !== 'string' ||
      item.length === 0 ||
      item.length > 256 ||
      !SAFE_STORY_ID_RE.test(item)
    ) {
      throw new Error('剧情编号清单包含无效编号');
    }
    const foldedId = item.toLocaleLowerCase();
    if (folded.has(foldedId)) {
      throw new Error(`剧情编号清单包含重复编号: ${item}`);
    }
    folded.add(foldedId);
    known.add(item);
  }
  return known;
};
