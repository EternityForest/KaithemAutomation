import { test, expect } from '@playwright/test';
import { login, logout, deleteModule } from './util';

test('test', async ({ page }) => {
    await login(page);


    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();


    await page.locator('input[name="apprise_target"]').click();
    await page.locator('input[name="apprise_target"]').fill('gnome://');
    await page.locator('form').filter({ hasText: 'This allows you to get' }).getByRole('button').click();
    await page.locator('input[name="url"]').click();
    await page.locator('input[name="url"]').fill('example.com');
    await page.locator('form').filter({ hasText: 'URL to redirect / to' }).getByRole('button').click();


    await page.getByText('lakehylia (0) Modules Devices Tags Tools Logout(admin) Close Options Options').click();
    await page.locator('form').filter({ hasText: 'URL to redirect / to' }).getByRole('button').click();
    
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();
    await expect(page.locator('input[name="apprise_target"]')).toHaveValue('gnome://');
    await expect(page.locator('input[name="url"]')).toHaveValue('example.com');
   
    await logout(page);
});