import { test, expect } from '@playwright/test';
import { login, logout, deleteModule } from './util';

test('test', async ({ page }) => {
    await login(page);


    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();


    await page.locator('input[name="url"]').click();
    await page.locator('input[name="url"]').fill('example.com');
    await page.locator('form').filter({ hasText: 'URL to redirect / to' }).getByRole('button').click();

    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: 'System Settings' }).click();
    await expect(page.locator('input[name="url"]')).toHaveValue('example.com');
   
    await logout(page);
});