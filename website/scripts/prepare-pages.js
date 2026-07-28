#!/usr/bin/env node

console.error(
  'Cloudflare Pages packaging is retired for this project because it would ' +
    'copy server code into public assets. Use the Cloudflare Workers commands ' +
    'documented in website/README.md.',
);
process.exitCode = 1;
