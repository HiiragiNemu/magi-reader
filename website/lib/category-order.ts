export const MAGIRECO_CATEGORY_ORDER = [
  'Unclassified',
  'character_story',
  'costume_story',
  'event_story',
  'login_story',
  'main_story',
  'mirror_story',
  'scene0_main',
  'scene0_sub',
  'general_voice',
] as const;

export const EXEDRA_CATEGORY_ORDER = [
  'exedra_main',
  'exedra_sub',
  'exedra_character',
  'exedra_portrait',
  'exedra_reaction',
  'exedra_namae',
  'exedra_dungeon',
  'exedra_battle',
] as const;

const CATEGORY_ORDER = new Map<string, number>(
  [...MAGIRECO_CATEGORY_ORDER, ...EXEDRA_CATEGORY_ORDER]
    .map((category, index) => [category, index]),
);

export const categoryOrder = (category: string): number =>
  CATEGORY_ORDER.get(category) ?? Number.MAX_SAFE_INTEGER;
