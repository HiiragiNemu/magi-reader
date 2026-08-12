const NON_SCENARIO_JSON_SUFFIXES = [
  ".import-report.json",
  ".provenance.json",
] as const;

const NON_SCENARIO_JSON_NAMES = new Set([
  "exedra_manifest.json",
  "general_voice_manifest.json",
]);

export function isScenarioDataFile(filename: string): boolean {
  const normalized = filename.toLowerCase();
  if (normalized.endsWith(".txt")) return true;
  if (!normalized.endsWith(".json")) return false;
  if (NON_SCENARIO_JSON_NAMES.has(normalized)) return false;
  return !NON_SCENARIO_JSON_SUFFIXES.some((suffix) =>
    normalized.endsWith(suffix),
  );
}

export function isScenarioMetadataFile(filename: string): boolean {
  const normalized = filename.toLowerCase();
  return (
    NON_SCENARIO_JSON_NAMES.has(normalized) ||
    NON_SCENARIO_JSON_SUFFIXES.some((suffix) => normalized.endsWith(suffix))
  );
}
