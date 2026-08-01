import { appendFileSync } from 'node:fs';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const CLOUDFLARE_API_ORIGIN = 'https://api.cloudflare.com';
const MAX_BUCKETS = 1_000;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const REQUEST_TIMEOUT_MS = 10_000;
const DISCOVERY_DEADLINE_MS = 120_000;

const ACCOUNT_ID_PATTERN = /^[a-f0-9]{32}$/iu;
const BUCKET_NAME_PATTERN = /^[a-z0-9](?:[a-z0-9-]{1,62}[a-z0-9])?$/u;
const MANAGED_DOMAIN_PATTERN = /^pub-[a-f0-9]{32}\.r2\.dev$/u;

class DiscoveryUnavailable extends Error {}

const annotationValue = (value) => String(value)
  .replaceAll('%', '%25')
  .replaceAll('\r', '%0D')
  .replaceAll('\n', '%0A');

const warning = (message) => {
  console.log(`::warning::${annotationValue(message)}`);
};

const requireConfiguration = (accountId, apiToken, targetDomain) => {
  if (!ACCOUNT_ID_PATTERN.test(accountId)) {
    throw new DiscoveryUnavailable(
      'CF_ACCOUNT_ID is missing or malformed; using the bounded HTTP voice fallback.',
    );
  }
  if (typeof apiToken !== 'string' || apiToken.length < 1 || apiToken.length > 8_192) {
    throw new DiscoveryUnavailable(
      'CF_API_TOKEN is missing or malformed; using the bounded HTTP voice fallback.',
    );
  }
  if (!MANAGED_DOMAIN_PATTERN.test(targetDomain)) {
    throw new Error(`Invalid managed R2 domain: ${targetDomain}`);
  }
};

const readJsonBounded = async (response) => {
  if (response.body == null) {
    throw new DiscoveryUnavailable('Cloudflare API returned an empty response.');
  }

  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      total += value.byteLength;
      if (total > MAX_RESPONSE_BYTES) {
        throw new DiscoveryUnavailable(
          'Cloudflare API response exceeded the 1 MiB discovery limit.',
        );
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    return JSON.parse(new TextDecoder().decode(merged));
  } catch {
    throw new DiscoveryUnavailable('Cloudflare API returned malformed JSON.');
  }
};

const apiRequest = async ({
  apiToken,
  fetchImpl,
  path,
  jurisdiction,
  deadline,
}) => {
  const remaining = deadline - Date.now();
  if (remaining <= 0) {
    throw new DiscoveryUnavailable(
      'R2 discovery reached its 120-second deadline; using the HTTP voice fallback.',
    );
  }

  const url = new URL(path, CLOUDFLARE_API_ORIGIN);
  const headers = {
    Accept: 'application/json',
    Authorization: `Bearer ${apiToken}`,
  };
  if (jurisdiction === 'eu' || jurisdiction === 'fedramp') {
    headers['cf-r2-jurisdiction'] = jurisdiction;
  }

  let response;
  try {
    response = await fetchImpl(url, {
      headers,
      redirect: 'error',
      signal: AbortSignal.timeout(Math.min(REQUEST_TIMEOUT_MS, remaining)),
    });
  } catch {
    throw new DiscoveryUnavailable(
      'Cloudflare R2 discovery request failed; using the HTTP voice fallback.',
    );
  }

  if (response.status === 401 || response.status === 403) {
    throw new DiscoveryUnavailable(
      'CF_API_TOKEN lacks Cloudflare R2 Storage Read permission; using the HTTP voice fallback.',
    );
  }
  if (response.status === 429) {
    throw new DiscoveryUnavailable(
      'Cloudflare R2 discovery was rate-limited; using the HTTP voice fallback.',
    );
  }

  const body = await readJsonBounded(response);
  if (!response.ok || body?.success !== true) {
    return {
      ok: false,
      status: response.status,
      body,
    };
  }
  return {
    ok: true,
    status: response.status,
    body,
  };
};

export const discoverR2VoiceBucket = async ({
  accountId,
  apiToken,
  targetDomain,
  fetchImpl = globalThis.fetch,
  now = Date.now,
}) => {
  requireConfiguration(accountId, apiToken, targetDomain);
  if (typeof fetchImpl !== 'function') {
    throw new TypeError('A fetch implementation is required.');
  }

  const deadline = now() + DISCOVERY_DEADLINE_MS;
  const listUrl = new URL(
    `/client/v4/accounts/${encodeURIComponent(accountId)}/r2/buckets`,
    CLOUDFLARE_API_ORIGIN,
  );
  listUrl.searchParams.set('per_page', String(MAX_BUCKETS));
  listUrl.searchParams.set('order', 'name');
  listUrl.searchParams.set('direction', 'asc');

  const listResponse = await apiRequest({
    apiToken,
    fetchImpl,
    path: `${listUrl.pathname}${listUrl.search}`,
    deadline,
  });
  const buckets = listResponse.body?.result?.buckets;
  if (!listResponse.ok || !Array.isArray(buckets)) {
    throw new DiscoveryUnavailable(
      'Cloudflare R2 bucket list was unavailable; using the HTTP voice fallback.',
    );
  }
  if (buckets.length > MAX_BUCKETS) {
    throw new DiscoveryUnavailable(
      `Cloudflare returned more than the bounded ${MAX_BUCKETS} R2 buckets; using the HTTP voice fallback.`,
    );
  }

  const cursor = listResponse.body?.result_info?.cursor;
  const names = new Set();
  for (const bucket of buckets) {
    if (typeof bucket?.name !== 'string' || !BUCKET_NAME_PATTERN.test(bucket.name)) {
      continue;
    }
    if (names.has(bucket.name)) {
      continue;
    }
    names.add(bucket.name);

    const domainResponse = await apiRequest({
      apiToken,
      fetchImpl,
      path: `/client/v4/accounts/${encodeURIComponent(accountId)}/r2/buckets/${encodeURIComponent(bucket.name)}/domains/managed`,
      jurisdiction: bucket.jurisdiction,
      deadline,
    });
    if (!domainResponse.ok) {
      if (domainResponse.status === 404) {
        continue;
      }
      throw new DiscoveryUnavailable(
        `Cloudflare managed-domain lookup failed for R2 bucket ${bucket.name}; using the HTTP voice fallback.`,
      );
    }

    const managed = domainResponse.body?.result;
    if (managed?.domain === targetDomain) {
      return {
        bucketName: bucket.name,
        domain: managed.domain,
        publicAccessEnabled: managed.enabled === true,
        listWasTruncated: typeof cursor === 'string' && cursor.length > 0,
      };
    }
  }

  if (typeof cursor === 'string' && cursor.length > 0) {
    throw new DiscoveryUnavailable(
      `The bounded first ${MAX_BUCKETS} R2 buckets did not contain the target domain; using the HTTP voice fallback.`,
    );
  }
  return null;
};

const parseTargetDomain = (argv) => {
  const index = argv.indexOf('--target-domain');
  if (index === -1 || typeof argv[index + 1] !== 'string') {
    throw new Error('--target-domain is required.');
  }
  return argv[index + 1];
};

const writeOutputs = ({ bucketName = '', discoveryStatus }) => {
  const githubOutput = process.env.GITHUB_OUTPUT;
  if (typeof githubOutput === 'string' && githubOutput.length > 0) {
    appendFileSync(
      githubOutput,
      `bucket_name=${bucketName}\ndiscovery_status=${discoveryStatus}\n`,
      { encoding: 'utf8' },
    );
  } else {
    console.log(`bucket_name=${bucketName}`);
    console.log(`discovery_status=${discoveryStatus}`);
  }
};

export const runDiscoveryCli = async ({
  argv = process.argv.slice(2),
  env = process.env,
  fetchImpl = globalThis.fetch,
} = {}) => {
  try {
    const targetDomain = parseTargetDomain(argv);
    const result = await discoverR2VoiceBucket({
      accountId: env.CLOUDFLARE_ACCOUNT_ID ?? '',
      apiToken: env.CLOUDFLARE_API_TOKEN ?? '',
      targetDomain,
      fetchImpl,
    });
    if (result == null) {
      warning(
        `No R2 bucket exactly matched ${targetDomain}; using the bounded HTTP voice fallback.`,
      );
      writeOutputs({ discoveryStatus: 'fallback' });
      return null;
    }

    console.log(
      `Discovered R2 voice bucket ${result.bucketName} for exact managed domain ${result.domain}.`,
    );
    if (!result.publicAccessEnabled) {
      warning(
        'The matching r2.dev domain is disabled, but the internal Worker R2 binding remains usable.',
      );
    }
    writeOutputs({
      bucketName: result.bucketName,
      discoveryStatus: 'bound',
    });
    return result;
  } catch (error) {
    if (error instanceof DiscoveryUnavailable) {
      warning(error.message);
      writeOutputs({ discoveryStatus: 'fallback' });
      return null;
    }
    throw error;
  }
};

const isMain = process.argv[1] != null
  && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  await runDiscoveryCli();
}
