/**
 * Browser wasm-bindgen glue adapted from the ISC-licensed `cricodecs`
 * hca-wasm package. See public/audio/LICENSE.cricodecs.txt.
 */
interface HcaWasmExports {
  memory: WebAssembly.Memory;
  decodeHca(
    returnPointer: number,
    pointer: number,
    length: number,
    keycode: bigint,
    subkey: number,
  ): void;
  __wbindgen_add_to_stack_pointer(delta: number): number;
  __wbindgen_malloc(size: number, align: number): number;
  __wbindgen_free(pointer: number, size: number, align: number): void;
}

const HCA_WASM_URL = '/audio/hca_wasm_bg.wasm';
const textDecoder = new TextDecoder('utf-8', {
  fatal: true,
  ignoreBOM: true,
});

let wasm: HcaWasmExports | null = null;
let initPromise: Promise<void> | null = null;

// wasm-bindgen reserves the first 132 slots.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const heap: any[] = new Array(128).fill(undefined);
heap.push(undefined, null, true, false);
let heapNext = heap.length;

function addHeapObject(value: unknown): number {
  if (heapNext === heap.length) heap.push(heap.length + 1);
  const index = heapNext;
  heapNext = heap[index] as number;
  heap[index] = value;
  return index;
}

function takeObject(index: number): unknown {
  const value = heap[index] as unknown;
  if (index >= 132) {
    heap[index] = heapNext;
    heapNext = index;
  }
  return value;
}

let cachedBytes: Uint8Array | null = null;
function memoryBytes(): Uint8Array {
  const current = wasm;
  if (!current) throw new Error('HCA decoder is not initialized');
  if (cachedBytes === null || cachedBytes.buffer !== current.memory.buffer) {
    cachedBytes = new Uint8Array(current.memory.buffer);
  }
  return cachedBytes;
}

let cachedView: DataView | null = null;
function memoryView(): DataView {
  const current = wasm;
  if (!current) throw new Error('HCA decoder is not initialized');
  if (cachedView === null || cachedView.buffer !== current.memory.buffer) {
    cachedView = new DataView(current.memory.buffer);
  }
  return cachedView;
}

function stringFromWasm(pointer: number, length: number): string {
  return textDecoder.decode(
    memoryBytes().subarray(pointer >>> 0, (pointer >>> 0) + length),
  );
}

export async function initHcaDecoder(): Promise<void> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const response = await fetch(HCA_WASM_URL, {
      cache: 'force-cache',
      credentials: 'same-origin',
    });
    if (!response.ok) {
      throw new Error(`HCA decoder failed to load (${response.status})`);
    }
    const contentLength = Number(response.headers.get('content-length') ?? '0');
    if (
      Number.isFinite(contentLength) &&
      contentLength > 0 &&
      contentLength > 256 * 1024
    ) {
      throw new Error('HCA decoder binary exceeds expected size');
    }
    const binary = await response.arrayBuffer();
    if (binary.byteLength > 256 * 1024) {
      throw new Error('HCA decoder binary exceeds expected size');
    }
    const instance = await WebAssembly.instantiate(binary, {
      __wbindgen_placeholder__: {
        __wbindgen_error_new(pointer: number, length: number): number {
          return addHeapObject(new Error(stringFromWasm(pointer, length)));
        },
      },
    });
    wasm = instance.instance.exports as unknown as HcaWasmExports;
    cachedBytes = null;
    cachedView = null;
  })();
  try {
    await initPromise;
  } catch (error) {
    initPromise = null;
    throw error;
  }
}

export function decodeHca(
  input: Uint8Array,
  keycode: bigint,
  subkey: number,
): Uint8Array {
  const current = wasm;
  if (!current) throw new Error('HCA decoder is not initialized');

  const returnPointer = current.__wbindgen_add_to_stack_pointer(-16);
  try {
    const inputPointer = current.__wbindgen_malloc(input.length, 1) >>> 0;
    memoryBytes().set(input, inputPointer);
    current.decodeHca(
      returnPointer,
      inputPointer,
      input.length,
      keycode,
      subkey,
    );

    const view = memoryView();
    const outputPointer = view.getInt32(returnPointer, true);
    const outputLength = view.getInt32(returnPointer + 4, true);
    const errorObject = view.getInt32(returnPointer + 8, true);
    const isError = view.getInt32(returnPointer + 12, true);
    if (isError) throw takeObject(errorObject);
    if (outputLength < 0 || outputLength > 32 * 1024 * 1024) {
      throw new Error('Decoded HCA output exceeds safety limit');
    }

    const output = memoryBytes()
      .subarray(
        outputPointer >>> 0,
        (outputPointer >>> 0) + outputLength,
      )
      .slice();
    current.__wbindgen_free(outputPointer, outputLength, 1);
    return output;
  } finally {
    current.__wbindgen_add_to_stack_pointer(16);
  }
}
