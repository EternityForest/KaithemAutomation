// End-to-end test for the container apps engine.
//
// Creates a container app through the module UI and checks the promises
// of the code/instance split: creating an app auto-creates an
// "APP-default" instance, and both the app (dev) and instance (admin)
// pages render.  Nothing is built or run here, so the test does not need
// any podman images.

import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

import { BASE, login, makeModule, deleteModule } from './util';

const MODULE = 'capp_e2e';
const APP = 'demo';

/** Wait until the resource JSON editor has loaded its schema default. */
async function waitForJsonEditor(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const editor = (globalThis as { editor?: { getValue(): unknown } })
      .editor;
    try {
      const value = editor?.getValue() as { service_user?: string };
      return value?.service_user === '__guest__';
    } catch {
      return false;
    }
  });
}

test('auto-creates a default instance and opens both admin pages', async ({
  page,
}) => {
  test.setTimeout(2_400_000);

  await login(page);
  await makeModule(page, MODULE);

  // Create the app.  Its schema default is already valid, so we only need
  // to name it and submit.
  await page.getByTestId('add-resource-button').click();
  await page.getByTestId('add-container_app').click();
  await page.getByLabel('Resource Name').fill(APP);
  await waitForJsonEditor(page);
  await page.getByRole('button', { name: 'Save' }).click();

  // The create redirect lands on the new app's resource page.
  await expect(page).toHaveURL(
    new RegExp(`/modules/module/${MODULE}/resource/${APP}$`)
  );

  // The module page lists both the app and the instance created for it.
  await page.goto(`${BASE}/modules/module/${MODULE}`);
  await expect(page.getByTestId('container-app-status')).toBeVisible();
  await expect(page.getByTestId('container-app-instance-status')).toBeVisible();
  await expect(page.getByTestId('container-app-instance-app')).toContainText(
    `${MODULE}:${APP}`
  );

  // The app dev page loads and offers the template/build actions.
  await page.getByTestId('container-app-open').click();
  await expect(page).toHaveURL(/type=app/);
  await expect(page.getByTestId('ca-title')).toHaveText(APP);
  await expect(page.getByTestId('ca-copy-template')).toBeVisible();
  await expect(page.getByTestId('ca-build')).toBeVisible();

  // The instance admin page loads and points back at its app.
  await page.goto(`${BASE}/modules/module/${MODULE}`);
  await page.getByTestId('container-app-instance-open').click();
  await expect(page).toHaveURL(/type=instance/);
  await expect(page.getByTestId('ca-app-ref')).toHaveText(`${MODULE}:${APP}`);
  await expect(page.getByTestId('ca-start')).toBeVisible();

  await deleteModule(page, MODULE);
});
