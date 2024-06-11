import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://localhost:8002/index');

    // Might already be on the login page
    if (await page.getByRole('link', { name: 'Login' }).isVisible()) {
      await page.getByRole('link', { name: 'Login' }).click();
    }
  
  await page.getByLabel('Username:').click();
  await page.getByLabel('Username:').fill('admin');
  await page.getByLabel('Password:').click();
  await page.getByLabel('Password:').fill('bad-pw');
  await page.getByRole('button', { name: 'Login as Registered User' }).click();
  await expect(page.getByRole('heading', { name: 'Error' })).toContainText('Error');
});