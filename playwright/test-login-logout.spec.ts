import { test, expect } from '@playwright/test';
import { login, logout } from './util';

test('test', async ({ page }) => {
  await login(page);
  await expect(page.getByRole('banner')).toContainText('admin');
  await logout(page);
  await expect(page.getByRole('heading', { name: 'Please Log In' })).toContainText('Log In');
});
