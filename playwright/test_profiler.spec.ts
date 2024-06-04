import { test, expect } from '@playwright/test';
import { login, logout } from './util';

test('test', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.locator('dt').filter({ hasText: 'Profiler' }).click();
    await page.getByRole('link', { name: 'Profiler' }).click();
    await page.getByRole('button', { name: 'Start' }).click();
    await expect(page.getByRole('main')).toContainText('Statistics');
    await page.getByRole('button', { name: 'Clear' }).click();
    await expect(page.getByRole('main')).toContainText('Statistics');
    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.getByRole('main')).toContainText('Start');

    await logout(page);
});