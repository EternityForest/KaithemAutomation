// End-to-end test for the Podman image manager plugin.
//
// Drives the full lifecycle against the shared Kaithem rootless podman
// storage the testing server uses: upload, export, tag, delete, and an
// oci-archive pull.  The fixture is a tiny OCI archive whose reference is
// ghcr.io/kljensen/hello-world-http:latest.

import path from 'node:path';

import { expect, test } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';

import { BASE, login } from './util';

const TEST_TAG = 'ghcr.io/kljensen/hello-world-http:latest';
const NEW_TAG = 'localhost/kaithem-pm-e2e:test';
// The exported filename sanitises the reference and appends the arch.
const TAR_NAME = 'ghcr.io-kljensen-hello-world-http-latest-amd64.tar';
const TAR_PATH = path.resolve('playwright/resources', TAR_NAME);
const EXPORT_PATH = '/dev/shm/pm-export.tar';

function rowFor(page: Page, tag: string): Locator {
  return page.locator(`[data-testid="pm-row"][data-tag="${tag}"]`);
}

/** The tag (or image id for untagged rows) of every rendered row, sorted. */
async function rowTags(page: Page): Promise<string[]> {
  const tags = await page
    .locator('[data-testid="pm-row"]')
    .evaluateAll((rows) => rows.map((row) => row.dataset.tag ?? ''));
  return tags.sort();
}

/** Wait until the list has finished loading whatever action kicked it off. */
async function waitForLoaded(page: Page): Promise<void> {
  await expect(page.getByTestId('pm-refresh')).toBeEnabled();
}

async function upload(page: Page, tarPath: string): Promise<void> {
  await page.getByTestId('pm-file-input').setInputFiles(tarPath);
  await page.getByTestId('pm-upload').click();
  await waitForLoaded(page);
}

async function deleteTag(page: Page, tag: string): Promise<void> {
  await rowFor(page, tag).getByTestId('pm-delete').click();
  await page.getByTestId('pm-delete-confirm').click();
  await expect(rowFor(page, tag)).toHaveCount(0);
  await waitForLoaded(page);
}

async function addTag(
  page: Page,
  image: string,
  newTag: string
): Promise<void> {
  await rowFor(page, image).getByTestId('pm-add-tag').click();
  await page.getByTestId('pm-tag-input').fill(newTag);
  await page.getByTestId('pm-tag-submit').click();
  await expect(page.getByTestId('pm-tag-dialog')).toHaveCount(0);
  await expect(rowFor(page, newTag)).toBeVisible();
  await waitForLoaded(page);
}

async function pull(page: Page, reference: string): Promise<void> {
  await page.getByTestId('pm-pull-input').fill(reference);
  await page.getByTestId('pm-pull').click();
  await waitForLoaded(page);
}

test('uploads, exports, tags, deletes, and pulls an OCI archive', async ({
  page,
}) => {
  test.setTimeout(600_000);
  page.setDefaultTimeout(60_000);

  await login(page);
  await page.goto(`${BASE}/podman`);
  await expect(page.getByTestId('pm-refresh')).toBeVisible();
  await waitForLoaded(page);

  // Start fresh: drop any tags a previous interrupted run left behind.
  for (const tag of [TEST_TAG, NEW_TAG]) {
    if ((await rowFor(page, tag).count()) > 0) {
      await deleteTag(page, tag);
    }
  }

  const baseline = await rowTags(page);

  // Upload the archive and confirm the restored tag is listed.
  await upload(page, TAR_PATH);
  await expect(rowFor(page, TEST_TAG)).toBeVisible();
  expect(await rowTags(page)).toHaveLength(baseline.length + 1);

  // Export it; the streamed download carries the arch-suffixed name.
  const downloadPromise = page.waitForEvent('download');
  await rowFor(page, TEST_TAG).getByTestId('pm-export').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(TAR_NAME);
  await download.saveAs(EXPORT_PATH);

  // Delete it from the store, then put it back.
  await deleteTag(page, TEST_TAG);
  expect(await rowTags(page)).toEqual(baseline);

  await upload(page, TAR_PATH);
  await expect(rowFor(page, TEST_TAG)).toBeVisible();
  expect(await rowTags(page)).toHaveLength(baseline.length + 1);

  // Add a second tag; both point at the same image.
  await addTag(page, TEST_TAG, NEW_TAG);
  await expect(rowFor(page, NEW_TAG)).toBeVisible();
  expect(await rowTags(page)).toHaveLength(baseline.length + 2);

  // Remove both tags and confirm nothing else was touched.
  await deleteTag(page, NEW_TAG);
  await deleteTag(page, TEST_TAG);
  expect(await rowTags(page)).toEqual(baseline);

  // Pull the fixture straight from its OCI archive, by absolute path.
  await pull(page, `oci-archive:${TAR_PATH}:${TEST_TAG}`);
  await expect(rowFor(page, TEST_TAG)).toBeVisible();
  expect(await rowTags(page)).toHaveLength(baseline.length + 1);

  // Clean up after ourselves.
  await deleteTag(page, TEST_TAG);
  expect(await rowTags(page)).toEqual(baseline);
});
