import { test, expect } from '@playwright/test';
import { login, logout, deleteModule, makeModule } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);

    await makeModule(page, 'testpageinnestedfolder');

    // Make a first folder
    await page.getByTestId('add-resource-button').click();

    await page.getByTestId('add-folder').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('testfolder');
    await page.getByRole('button', { name: 'Submit' }).click();

    //Go in the folder
    await page.getByRole('link', { name: '󰉖 testfolder' }).click();

    // Make a nested folder in the folder
    await page.getByTestId('add-resource-button').click();
    await page.getByTestId('add-folder').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('testfolder2');
    await page.getByRole('button', { name: 'Submit' }).click();


    // Go to the root of the module
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'testpageinnestedfolder' }).click();


    // Go in the first folder
    await page.getByRole('link', { name: '󰉖 testfolder' }).click();
    // Go in the nested folder
    await page.getByRole('link', { name: '󰉖 testfolder2' }).click();

    //Make a page there
    await page.getByTestId('add-resource-button').click();
    await page.getByTestId('add-page').click();
    // On page editor, save and goto
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('page');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('button', { name: 'Save and go to page' }).click();

    // Make sure it worked
    await expect(page.locator('section')).toContainText('Content here');
    await expect(page.getByRole('heading')).toContainText('page');

    await deleteModule(page, 'testpageinnestedfolder');
    await logout(page);

})