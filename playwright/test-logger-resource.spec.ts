import { test, expect } from '@playwright/test';
import { login, logout, deleteModule, makeModule } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2_400_000);

    await login(page);

    await makeModule(page, 'test_logger');


    // Add a logger to that module
    await page.getByTestId('add-resource-button').click();
    await page.getByTestId('add-logger').click();
    await page.getByLabel('Logger Name').click();
    await page.getByLabel('Logger Name').fill('testlogger');
    await page.getByLabel('Tag Point to Log').click();
    await page.getByLabel('Tag Point to Log').fill('/system/sensors/temp/coretemp');
    await page.getByLabel('Interval(seconds)').click();
    await page.getByLabel('Interval(seconds)').fill('1');
    await page.getByRole('button', { name: 'Submit' }).click();

    // Should be on the edit page, confirm that works
    await page.getByRole('button', { name: 'Submit' }).click();

    // Go to the logger UI and confirm that it at least doesn't error
    await page.getByRole('button', { name: 'View Logs' }).click();
    await expect(page.getByRole('main')).toContainText('Export Data');
    await expect(page.locator('h3')).toContainText('Recent Log Data');

    await deleteModule(page, 'test_logger');
    await logout(page);
});