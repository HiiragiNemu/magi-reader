export type ReaderLanguageMode = 'cn' | 'split' | 'jp';
export type ReaderBilingualLayout = 'side-by-side' | 'stacked';
export type ReaderLanguagePane = 'cn' | 'jp';

/**
 * Keep one CN/JP alignment row as the indivisible visual unit. In stacked mode
 * the separator belongs after the complete pair, never between its languages.
 */
export function bilingualStoryPairClass(
  mode: ReaderLanguageMode,
  layout: ReaderBilingualLayout,
): string {
  if (mode === 'split' && layout === 'stacked') {
    return 'magi-bilingual-pair magi-bilingual-pair-stacked flex-col gap-2 py-3';
  }
  if (layout === 'side-by-side') {
    return 'magi-bilingual-pair magi-bilingual-pair-responsive flex-col py-2 md:flex-row md:gap-4';
  }
  return 'magi-bilingual-pair flex-col gap-2 py-1';
}

export function bilingualLanguagePaneClass(
  mode: ReaderLanguageMode,
  layout: ReaderBilingualLayout,
  pane: ReaderLanguagePane,
): string {
  if (mode !== 'split') return 'w-full';
  if (layout === 'stacked') return 'w-full';
  return pane === 'cn'
    ? 'md:w-1/2'
    : 'mt-1 border-current border-opacity-10 md:mt-0 md:w-1/2 md:border-l md:pl-4';
}
