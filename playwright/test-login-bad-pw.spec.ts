import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://localhost:8002/index');
  await page.getByLabel('Username:').click();
  await page.getByLabel('Username:').fill('admin');
  await page.getByLabel('Password:').click();
  await page.getByLabel('Password:').fill('bad-pw');
  await page.getByRole('button', { name: 'Login as Registered User' }).click();
  await expect(page.getByRole('banner')).toContainText('Login');
});