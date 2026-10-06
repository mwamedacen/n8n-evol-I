#!/usr/bin/env node
// Shim: read workflow JSON from stdin, layout via @n8n/workflow-sdk, write to stdout.
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

// Resolve the pinned dependency from a mutable cache, not this installation.
if (!process.argv[2]) throw new Error('SDK cache directory is required');
const requireFromCache = createRequire(resolve(process.argv[2], 'package.json'));
const sdk = await import(pathToFileURL(requireFromCache.resolve('@n8n/workflow-sdk')).href);
const { layoutWorkflowJSON } = sdk.default ?? sdk;

let raw = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { raw += chunk; });
process.stdin.on('end', () => {
  try {
    const workflow = JSON.parse(raw);
    const laid = layoutWorkflowJSON(workflow);
    process.stdout.write(JSON.stringify(laid));
  } catch (err) {
    process.stderr.write(String(err) + '\n');
    process.exit(1);
  }
});
process.stdin.on('error', err => {
  process.stderr.write(String(err) + '\n');
  process.exit(1);
});
