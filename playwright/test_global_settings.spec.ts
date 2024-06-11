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
    await page.locator('input[name="warningbeeptime"]').click({
        clickCount: 3
    });

    await page.locator('input[name="errorsound"]').click();
    await page.locator('input[name="errorsound"]').fill('error.ogg');
    await page.locator('input[name="warningsound"]').click();
    await page.locator('input[name="warningsound"]').fill('error.ogg');
    await page.locator('input[name="soundcard"]').dblclick();
    await page.locator('input[name="soundcard"]').fill('__disable__default');

    await page.locator('input[name="soundcard"]').fill('default');
    await page.locator('input[name="warningbeeptime"]').fill('3601');
    await page.locator('input[name="errorbeeptime"]').click();
    await page.locator('input[name="errorbeeptime"]').fill('3601');
    await page.locator('input[name="critbeeptime"]').dblclick();
    await page.locator('input[name="critbeeptime"]').click();
    await page.locator('input[name="critbeeptime"]').fill('15');
    await page.getByRole('button', { name: 'Save sound settings' }).click();
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();
    await expect(page.locator('input[name="apprise_target"]')).toHaveValue('gnome://');
    await expect(page.locator('input[name="url"]')).toHaveValue('example.com');
    await expect(page.locator('input[name="warningbeeptime"]')).toHaveValue('3601.0');
    await page.locator('input[name="warningsound"]').click();
    await expect(page.locator('input[name="warningsound"]')).toHaveValue('error.ogg');
    await expect(page.locator('input[name="errorbeeptime"]')).toHaveValue('3601.0');
    await expect(page.locator('input[name="errorsound"]')).toHaveValue('error.ogg');
    await expect(page.locator('input[name="critbeeptime"]')).toHaveValue('15.0');
    await expect(page.locator('input[name="critsound"]')).toHaveValue('error.ogg');
    await expect(page.locator('input[name="soundcard"]')).toHaveValue('default');

    await logout(page);
});