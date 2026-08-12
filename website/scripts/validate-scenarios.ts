import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { parseStoryContent } from '../lib/story-parser.ts';
import {
  isScenarioDataFile,
  isScenarioMetadataFile,
} from '../lib/scenario-file-policy.ts';

const sourceRoot = process.argv[2];
if (!sourceRoot) {
  console.error('Usage: npm run validate:scenarios -- <Scenarios directory>');
  process.exitCode = 2;
} else if (!fs.existsSync(sourceRoot) || !fs.statSync(sourceRoot).isDirectory()) {
  console.error(`Scenario directory does not exist: ${sourceRoot}`);
  process.exitCode = 2;
} else {
  const pending = [path.resolve(sourceRoot)];
  const files: string[] = [];
  let skippedMetadataFiles = 0;

  while (pending.length > 0) {
    const current = pending.pop();
    if (!current) continue;
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(fullPath);
      else if (isScenarioDataFile(entry.name)) files.push(fullPath);
      else if (isScenarioMetadataFile(entry.name)) skippedMetadataFiles++;
    }
  }

  const summary = {
    jsonFiles: 0,
    textFiles: 0,
    exedraJson: 0,
    plainText: 0,
    scene0Text: 0,
    lines: 0,
    emptyFiles: 0,
    warnings: 0,
    skippedMetadataFiles,
    failures: [] as Array<{ file: string; error: string }>,
  };

  for (const filePath of files.sort()) {
    const relativePath = path.relative(sourceRoot, filePath);
    try {
      const raw = fs.readFileSync(filePath, 'utf8');
      const result = parseStoryContent(raw, {
        filename: path.basename(filePath),
        mergeConsecutiveTextLines: false,
      });

      if (/\.json$/i.test(filePath)) summary.jsonFiles++;
      else summary.textFiles++;
      if (result.format === 'exedra-json') summary.exedraJson++;
      if (result.format === 'plain-text') summary.plainText++;
      if (result.format === 'scene0-text') summary.scene0Text++;
      summary.lines += result.lines.length;
      summary.warnings += result.warnings.length;
      if (result.lines.length === 0) summary.emptyFiles++;
    } catch (error) {
      summary.failures.push({
        file: relativePath,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  console.log(JSON.stringify(summary, null, 2));
  if (summary.failures.length > 0) process.exitCode = 1;
}
