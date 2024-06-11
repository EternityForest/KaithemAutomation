import { test, expect } from '@playwright/test';
import { login, logout, makeModule, deleteModule, makeTagPoint } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);

    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: '󰐕 Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('test_search');
    await page.getByRole('button', { name: 'Submit' }).click();

    // Make the page which should appear in search results
    await page.getByTestId('add-page').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('search_result');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('button', { name: 'Save and go to page' }).click();

    //Searh for that page
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'test_search' }).click();
    await page.getByPlaceholder('Search this module').click();
    await page.getByPlaceholder('Search this module').fill('content here');
    await page.getByRole('button', { name: '󰜏' }).click();
    await expect(page.getByRole('listitem')).toContainText('search_result');

    await deleteModule(page, 'test_search');

    await logout(page);
});