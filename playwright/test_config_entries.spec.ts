import { test, expect } from '@playwright/test';
import { login, logout, deleteModule, makeModule } from './util';

test('test', async ({ page }) => {
    test.setTimeout(4800000);

    await login(page);

    await makeModule(page, 'test_config');

    await page.getByRole('button', { name: 'Add Resource' }).click();
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
    await page.getByTestId("delete-resource-button").click();
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: '󰢻 System Settings' }).click();

    await expect(page.getByLabel('test_key test_val')).not.toBeVisible();


    await deleteModule(page, 'test_config');

    await logout(page);
});