import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://localhost:8002/');
  await page.getByRole('link', { name: '󰌆 Login' }).click();
  await page.getByLabel('Username:').click();
  await page.getByLabel('Username:').fill('admin');
  await page.getByLabel('Password:').click();
  await page.getByLabel('Password:').fill('test-admin-password');
  await page.getByRole('button', { name: 'Login as Registered User' }).click();
  await expect(page.getByRole('banner')).toContainText('admin');
  await page.getByRole('button', { name: '󰌆 Logout(admin)' }).click();
  await expect(page.getByRole('banner')).toContainText('Login');
});
