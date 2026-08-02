export type BoundedFetchOptions = {
  label: string;
  maxBytes: number;
  timeoutMs: number;
};

const validatePositiveSafeInteger = (value: number, label: string): void => {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${label}无效`);
  }
};

export const cancelResponseBody = async (
  response: Response,
  reason: string,
): Promise<void> => {
  try {
    await response.body?.cancel(reason);
  } catch {
    // Cancellation is best-effort. Preserve the original failure instead of
    // replacing it with an upstream stream cancellation error.
  }
};

const abortError = (label: string): Error => new Error(`${label}读取超时`);

/**
 * Read a response incrementally and stop before retaining more than maxBytes.
 * The optional signal also bounds a body that returns headers and then stalls.
 */
export const readBoundedResponseBytes = async (
  response: Response,
  maxBytes: number,
  label: string,
  signal?: AbortSignal,
): Promise<Uint8Array> => {
  validatePositiveSafeInteger(maxBytes, `${label}大小限制`);
  const tooLargeMessage = `${label}超过大小限制`;
  const declaredRaw = response.headers.get('content-length');
  if (declaredRaw !== null && /^\d+$/u.test(declaredRaw.trim())) {
    const declared = Number(declaredRaw);
    if (!Number.isSafeInteger(declared) || declared > maxBytes) {
      await cancelResponseBody(response, tooLargeMessage);
      throw new Error(tooLargeMessage);
    }
  }

  const reader = response.body?.getReader();
  if (!reader) return new Uint8Array(0);

  const chunks: Uint8Array[] = [];
  let total = 0;
  let completed = false;
  let rejectAborted: ((reason: Error) => void) | null = null;
  const aborted = new Promise<never>((_resolve, reject) => {
    rejectAborted = reject;
  });
  const onAbort = () => {
    const error = abortError(label);
    void reader.cancel(error.message).catch(() => undefined);
    rejectAborted?.(error);
  };
  signal?.addEventListener('abort', onAbort, { once: true });

  try {
    if (signal?.aborted) onAbort();
    for (;;) {
      const result = signal
        ? await Promise.race([reader.read(), aborted])
        : await reader.read();
      if (result.done) {
        completed = true;
        break;
      }
      total += result.value.byteLength;
      if (total > maxBytes) {
        void reader.cancel(tooLargeMessage).catch(() => undefined);
        throw new Error(tooLargeMessage);
      }
      chunks.push(result.value);
    }
  } catch (error) {
    if (!completed) {
      void reader.cancel(
        error instanceof Error ? error.message : `${label}读取失败`,
      ).catch(() => undefined);
    }
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
    try {
      reader.releaseLock();
    } catch {
      // A raced read can still own the lock briefly after abort. The reader is
      // already cancelled, so leaving release to stream cleanup is bounded.
    }
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
};

/**
 * Bound both response-header wait and streaming body read with one timeout.
 * The caller owns URL/origin policy and should use redirect: 'error' for fixed
 * upstreams.
 */
export const fetchBoundedResponseBytes = async (
  fetchResponse: (signal: AbortSignal) => Promise<Response>,
  { label, maxBytes, timeoutMs }: BoundedFetchOptions,
): Promise<Uint8Array> => {
  validatePositiveSafeInteger(timeoutMs, `${label}超时`);
  const controller = new AbortController();
  let timedOut = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      const error = abortError(label);
      controller.abort(error);
      reject(error);
    }, timeoutMs);
  });

  const responsePromise = Promise.resolve()
    .then(() => fetchResponse(controller.signal))
    .then(response => {
      if (timedOut) void cancelResponseBody(response, `${label}读取超时`);
      return response;
    });

  let response: Response | null = null;
  try {
    response = await Promise.race([responsePromise, timeout]);
    if (!response.ok) {
      await cancelResponseBody(response, `${label} HTTP ${response.status}`);
      throw new Error(`${label}读取失败（HTTP ${response.status}）`);
    }
    return await Promise.race([
      readBoundedResponseBytes(response, maxBytes, label, controller.signal),
      timeout,
    ]);
  } catch (error) {
    if (response) {
      await cancelResponseBody(
        response,
        error instanceof Error ? error.message : `${label}读取失败`,
      );
    }
    throw error;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
};
