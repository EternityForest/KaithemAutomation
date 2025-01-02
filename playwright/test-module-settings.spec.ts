import { test, expect } from '@playwright/test';
import { login,makeModule,deleteModule } from "./util";

test('test', async ({ page }) => {
    await login(page);
    
  await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await makeModule(page, 'test_module_settings');
    await page.getByTestId('add-resource-button').click();
    await page.getByTestId('add-page').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('test');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: '󱒕 Modules' }).click();


    // Move to an ext location
    await page.getByRole('link', { name: 'test_module_settings' }).click();
    await page.getByTestId("module-save-location").fill('/dev/shm/test_ext_module_location');
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.getByRole('heading', { name: 'Module test_module_settings' })).toBeVisible();
    await expect( page.getByTestId("module-save-location")).toHaveValue('/dev/shm/test_ext_module_location');
    await expect(page.getByRole('main')).not.toContainText('ERRORHASHINGMODULE');

   // Rename and set some metadata
    await page.locator('input[name="name"]').fill('test_module_settings2');
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.getByRole('main')).not.toContainText('ERRORHASHINGMODULE');
    await expect( page.getByTestId("module-save-location")).not.toBeEmpty();
   
    await page.locator('textarea[name="description"]').click();
    await page.locator('textarea[name="description"]').fill('test');
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await expect(page.locator('textarea[name="description"]')).toHaveValue('test');

    // Use the file manager page to see if it saved where we think
    await page.getByRole('link', { name: '󰢻 Tools' }).click();
    await page.getByRole('link', { name: 'File Manager', exact: true }).click();
    await page.getByRole('link', { name: 'dev/' }).click();
    await page.getByRole('link', { name: 'shm/' }).click();
    await page.getByRole('link', { name: 'test_ext_module_location/' }).click();
    await expect(page.getByRole('link', { name: 'test.html' })).toBeVisible();

    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByLabel('Delete').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('test_module_settings2');
    await page.getByRole('button', { name: 'Submit' }).click();

    await expect(page.getByRole('link', { name: 'test_module_settings2' })).toBeHidden  ();
});