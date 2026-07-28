const ID_RE = /^[a-f0-9]{32}$/iu;
const PLACEHOLDER_ID = '00000000000000000000000000000000';

export const stripAnsi = (value) =>
  value.replace(/\u001b\[[0-9;]*m/gu, '');

export const collectNamespaceObjects = (value, result = []) => {
  if (Array.isArray(value)) {
    for (const item of value) collectNamespaceObjects(item, result);
  } else if (value && typeof value === 'object') {
    const id = typeof value.id === 'string' ? value.id.trim() : '';
    const title = typeof value.title === 'string'
      ? value.title.trim()
      : typeof value.name === 'string'
        ? value.name.trim()
        : '';
    if (ID_RE.test(id) && title) result.push({ id, title });
    for (const nested of Object.values(value)) {
      if (nested && typeof nested === 'object') {
        collectNamespaceObjects(nested, result);
      }
    }
  }
  return result;
};

const lineContainsExactTitle = (line, title) => {
  let from = 0;
  while (from <= line.length) {
    const index = line.indexOf(title, from);
    if (index < 0) return false;
    const before = index > 0 ? line[index - 1] : '';
    const after = line[index + title.length] ?? '';
    const identifier = /[A-Za-z0-9_-]/u;
    if ((!before || !identifier.test(before)) && (!after || !identifier.test(after))) {
      return true;
    }
    from = index + title.length;
  }
  return false;
};

export const parseNamespaceList = (raw, exactTitle) => {
  const output = stripAnsi(String(raw)).trim();
  const matches = [];
  const jsonCandidates = [output];

  const firstArray = output.indexOf('[');
  const lastArray = output.lastIndexOf(']');
  if (firstArray >= 0 && lastArray > firstArray) {
    jsonCandidates.push(output.slice(firstArray, lastArray + 1));
  }
  const firstObject = output.indexOf('{');
  const lastObject = output.lastIndexOf('}');
  if (firstObject >= 0 && lastObject > firstObject) {
    jsonCandidates.push(output.slice(firstObject, lastObject + 1));
  }

  for (const candidate of jsonCandidates) {
    try {
      for (const item of collectNamespaceObjects(JSON.parse(candidate))) {
        if (item.title === exactTitle) matches.push(item.id.toLowerCase());
      }
    } catch {
      // Wrangler versions differ; fall through to table/text parsing.
    }
  }

  for (const line of output.split(/\r?\n/gu)) {
    if (!lineContainsExactTitle(line, exactTitle)) continue;
    for (const match of line.matchAll(/[a-f0-9]{32}/giu)) {
      matches.push(match[0].toLowerCase());
    }
  }

  const unique = [...new Set(matches)];
  if (unique.length === 0) {
    throw new Error(
      `Wrangler 返回中没有找到名称完全等于 ${JSON.stringify(exactTitle)} 的 KV namespace。`,
    );
  }
  if (unique.length !== 1) {
    throw new Error(
      `KV namespace 名称 ${JSON.stringify(exactTitle)} 对应多个 ID：${unique.join(', ')}`,
    );
  }
  return unique[0];
};

export const replaceExactlyOnce = (
  source,
  expression,
  replacement,
  label,
) => {
  const flags = expression.flags.includes('g')
    ? expression.flags
    : `${expression.flags}g`;
  const matches = source.match(new RegExp(expression.source, flags));
  if (!matches || matches.length !== 1) {
    throw new Error(
      `${label} 预期匹配 1 次，实际 ${matches?.length ?? 0} 次`,
    );
  }
  return source.replace(expression, replacement);
};

export const rewriteTestConfig = ({
  source,
  workerName,
  namespaceId,
}) => {
  if (!/^[a-z0-9][a-z0-9-]{0,62}$/u.test(workerName)) {
    throw new Error(`测试 Worker 名称无效：${workerName}`);
  }
  if (!ID_RE.test(namespaceId) || namespaceId === PLACEHOLDER_ID) {
    throw new Error('测试 KV ID 无效或仍为全零占位值');
  }

  let result = replaceExactlyOnce(
    source,
    /"name"\s*:\s*"[^"]+"/u,
    `"name": ${JSON.stringify(workerName)}`,
    'Worker name',
  );
  result = replaceExactlyOnce(
    result,
    /"service"\s*:\s*"[^"]+"/u,
    `"service": ${JSON.stringify(workerName)}`,
    'WORKER_SELF_REFERENCE service',
  );
  if (result.includes(PLACEHOLDER_ID)) {
    throw new Error('生成配置仍包含全零 KV ID');
  }
  if (!result.includes(namespaceId)) {
    throw new Error('生成配置没有包含解析出的测试 KV ID');
  }
  return result;
};
