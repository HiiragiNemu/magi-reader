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
    list(options?: SubmissionKvListOptions): Promise<SubmissionKvListResult>;
  }

  interface CloudflareEnv {
    SUBMISSIONS_KV?: SubmissionKvNamespace;
    SUBMISSIONS_ADMIN_TOKEN?: string;
  }
}
