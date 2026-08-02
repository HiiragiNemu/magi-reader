export {};

declare global {
  type SubmissionKvPutOptions = {
    expirationTtl?: number;
  };

  type SubmissionKvListOptions = {
    prefix?: string;
    limit?: number;
    cursor?: string;
  };

  type SubmissionKvListResult = {
    keys: Array<{ name: string }>;
    list_complete: boolean;
    cursor?: string;
  };

  interface SubmissionKvNamespace {
    get(key: string): Promise<string | null>;
    put(
      key: string,
      value: string,
      options?: SubmissionKvPutOptions,
    ): Promise<void>;
    delete(key: string): Promise<void>;
    list(options?: SubmissionKvListOptions): Promise<SubmissionKvListResult>;
  }

  interface CloudflareAssetsBinding {
    fetch(request: Request | string): Promise<Response>;
  }

  type CloudflareR2Range = {
    offset?: number;
    length?: number;
    suffix?: number;
  };

  interface CloudflareR2ObjectBody {
    body: ReadableStream<Uint8Array>;
    size: number;
    etag: string;
    httpEtag: string;
    range?: {
      offset: number;
      length: number;
    };
  }

  interface CloudflareR2Bucket {
    get(
      key: string,
      options?: { range?: CloudflareR2Range },
    ): Promise<CloudflareR2ObjectBody | null>;
  }

  interface CloudflareEnv {
    ASSETS?: CloudflareAssetsBinding;
    MAGIRECO_VOICE_R2?: CloudflareR2Bucket;
    SUBMISSIONS_KV?: SubmissionKvNamespace;
    SUBMISSIONS_ADMIN_TOKEN?: string;
    TURNSTILE_SITE_KEY?: string;
    TURNSTILE_SECRET_KEY?: string;
    TURNSTILE_ALLOWED_HOSTNAMES?: string;
    PROOFREADING_TARGET_BRANCH?: string;
    PROOFREADING_SOURCE_COMMIT?: string;
    PROOFREADING_GITHUB_REPO?: string;
    PROOFREADING_GITHUB_TOKEN?: string;
    STORY_JSON_GITHUB_TOKEN?: string;
    PROOFREADING_ALLOW_GITHUB_ADMIN?: string;
    PROOFREADING_TURNSTILE_TEST_MODE?: string;
    EXEDRA_WIKI_BASE_URL?: string;
  }
}
