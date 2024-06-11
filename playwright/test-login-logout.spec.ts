import { test, expect } from '@playwright/test';
import { login, logout } from './util';

test('test', async ({ page }) => {
  await login(page);
  await expect(page.getByRole('banner')).toContainText('admin');
  await logout(page);
  await page.getByRole('link', { name: '󰘚 Devices' }).click();
  await expect(page.locator('h2')).toContainText('Please Log In');
});
