import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

const repositoryRoot = path.resolve(process.cwd(), '..');
const script = path.resolve(repositoryRoot, 'tools', 'run_python_checks.py');
const candidates = process.platform === 'win32'
  ? [
      { command: 'py', prefix: ['-3'] },
      { command: 'python', prefix: [] },
      { command: 'python3', prefix: [] },
    ]
  : [
      { command: 'python3', prefix: [] },
      { command: 'python', prefix: [] },
    ];

let lastError = '';
for (const candidate of candidates) {
  const version = spawnSync(
    candidate.command,
    [...candidate.prefix, '--version'],
    {
      cwd: repositoryRoot,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    },
  );
  if (version.error?.code === 'ENOENT') continue;
  if (version.error || version.status !== 0) {
    lastError = `${candidate.command}: ${version.error ?? version.stderr ?? version.stdout}`;
    continue;
  }

  const run = spawnSync(
    candidate.command,
    [...candidate.prefix, script, '--verbose'],
    {
      cwd: repositoryRoot,
      stdio: 'inherit',
      windowsHide: true,
    },
  );
  if (run.error) throw run.error;
  if (run.status !== 0) process.exit(run.status ?? 2);
  console.log(
    `Python checks used ${candidate.command} ${candidate.prefix.join(' ')}`.trim(),
  );
  process.exit(0);
}

throw new Error(
  `没有找到可用的 Python 3 解释器。已尝试：${candidates.map(item => item.command).join(', ')}${lastError ? `；最后错误：${lastError}` : ''}`,
);
