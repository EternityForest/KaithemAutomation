import { test, expect } from '@playwright/test';
import { login, logout, login_as } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('test_folders');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByTestId('add-folder').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('dir1');
    await page.getByRole('button', { name: 'Submit' }).click();

    await page.getByTestId('add-file').click();
    await page.locator('#upload').setInputFiles('badges/linux.png');
    await page.getByRole('button', { name: 'Upload' }).click();
    await page.getByRole('link', { name: '󰉖 dir1' }).click();
    await page.getByTestId('add-file').click();
    await page.locator('#upload').click();
    await page.locator('#upload').setInputFiles('badges/gpl-v3.png');
    await page.getByRole('button', { name: 'Upload' }).click();
    await expect(page.getByRole('term')).toContainText('gpl-v3.png');

    await logout(page);
});