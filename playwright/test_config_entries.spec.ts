import { test, expect } from '@playwright/test';
import { login, logout, deleteModule } from './util';

test('test', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: '󰐕 Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('test_config');
    await page.getByText('Name of New Module Choose an').click();

    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByTestId('add-config').click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill('config_entry');
    await page.getByLabel('Resource Name').press('Tab');
    await page.getByLabel('Config Key').fill('test_key');
    await page.getByLabel('Config Key').press('Tab');
    await page.getByLabel('Config Value').fill('test_val');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('button', { name: 'Submit' }).click();


    await page.getByRole('link', { name: '󰢻 config_entry (config)' }).click();
    await expect(page.getByLabel('test_key test_val')).toHaveValue('test_val');
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();
    await expect(page.locator('dl')).toContainText('test_key');
    await expect(page.locator('dl')).toContainText('test_val');
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'test_config' }).click();
    await page.getByRole('link', { name: '󰆴 Delete' }).click();
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();

    await expect(page.getByLabel('test_key test_val')).not.toBeVisible();


    await deleteModule(page, 'test_config');

    await logout(page);
});