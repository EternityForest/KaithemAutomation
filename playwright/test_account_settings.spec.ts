import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://localhost:8002/login?go=aHR0cDovL2xvY2FsaG9zdDo4MDAyLw==&maxgotime-1717372653.6831186');
  await page.getByLabel('Username:').click();
  await page.getByLabel('Username:').fill('admin');
  await page.getByLabel('Username:').press('Tab');
  await page.getByLabel('Password:').fill('test-admin-password');
  await page.getByLabel('Password:').press('Enter');
  await page.getByRole('link', { name: '󰢻 Tools' }).click();
  await page.getByRole('link', { name: '󰀄 My Account' }).click();
  await expect(page.locator('h1')).toContainText('My Account');
  await expect(page.getByRole('main')).toContainText('__all_permissions__');
  await page.locator('input[name="old"]').click();
  await page.locator('input[name="old"]').fill('test-admin-password');
  await page.locator('input[name="new"]').click();
  await page.locator('input[name="new"]').fill('test-admin-password');
  await page.locator('input[name="new2"]').click();
  await page.locator('input[name="new2"]').fill('test-admin-password');
  await page.getByRole('button', { name: 'Change Password' }).click();
});