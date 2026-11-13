// Fail the build if any dependency or build output ships a compiled
// native addon.
//
// A Kaithem container app builds a platform independent directory of
// files, so a compiled `.node` addon, which only loads on the machine
// that produced it, is never allowed.  Anything that needs native code
// must be built into a proper multi platform image elsewhere; that is
// out of scope here.  `bun install --ignore-scripts` already prevents
// dependencies from compiling native code, and this check catches any
// that still ship a prebuilt `.node` file.

import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { exit } from 'node:process';

/** Roots that must not contain a compiled addon. */
const ROOTS = ['node_modules', 'dist'];

/** Suffix of a compiled native addon. */
const NATIVE_SUFFIX = '.node';

function findNativeAddons(root: string): string[] {
  const found: string[] = [];
  const stack: string[] = [root];
  while (stack.length > 0) {
    const directory = stack.pop();
    if (directory === undefined) {
      break;
    }
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        stack.push(path);
      } else if (entry.isFile() && entry.name.endsWith(NATIVE_SUFFIX)) {
        found.push(path);
      }
    }
  }
  return found;
}

const offenders = ROOTS.filter((root) => existsSync(root)).flatMap(
  findNativeAddons
);

if (offenders.length > 0) {
  console.error('Compiled native addons are not allowed:');
  for (const path of offenders) {
    console.error(`  ${path}`);
  }
  console.error(
    'Build a portable image with proper tools instead of shipping a ' +
      'prebuilt addon into a static project.'
  );
  exit(1);
}

console.log('No compiled native addons found.');
