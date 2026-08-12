export const normalizedOfficialTitle = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim();
  return normalized || undefined;
};

export const resolveOfficialChapterTitle = (
  stories: ReadonlyArray<{ official_tw_chapter_title?: string }>,
  fallback: string,
): string => {
  const titles = [...new Set(
    stories
      .map(story => normalizedOfficialTitle(story.official_tw_chapter_title))
      .filter((value): value is string => Boolean(value)),
  )];
  return titles.length === 1 ? titles[0] : fallback;
};

export const resolveOfficialSectionTitle = (
  titles: readonly string[] | undefined,
  sectionNumber: string | number | undefined,
  fallback: string,
): string => {
  const numeric = Number(sectionNumber);
  if (!Number.isInteger(numeric) || numeric < 1) return fallback;
  return normalizedOfficialTitle(titles?.[numeric - 1]) ?? fallback;
};
