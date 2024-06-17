import { test, expect, chromium } from '@playwright/test';
import { login, logout, makeModule, deleteModule, makeTagPoint } from './util';

test('test', async ({ page }) => {
    test.setTimeout(2400000);

    await login(page);


    const brows = await chromium.launch();

    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: '󰐕 Add' }).click();
    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill('test_static_server');
    await page.getByRole('button', { name: 'Submit' }).click();

    // Make a /public folder
    await page.getByTestId('add-folder').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('public');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('link', { name: '󰉖 public' }).click();

    // Add a file to folder
    await page.getByTestId('add-file').click();
    await page.locator('#upload').setInputFiles('badges/linux.png');
    await page.getByRole('button', { name: 'Upload' }).click();

    // Add a static server at /pages/test_static_server/static pointing at /public
    // Which is the default for the server resources
    await page.getByRole('link', { name: 'test_static_server' }).click();
    await page.getByTestId('add-fileserver').click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill('static');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('button', { name: 'Submit' }).click();

    // Ensure that it's serving the file
    await page.goto('http://localhost:8002/pages/test_static_server/static/linux.png');
    await expect(page.getByRole('img')).toBeVisible();
    await page.goto('http://localhost:8002/');

    // Ensure browsing it works
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'test_static_server' }).click();
    await page.getByRole('link', { name: 'Browse' }).click();
    await expect(page.locator('dl')).toContainText('linux.png');
    await page.getByRole('link', { name: 'linux.png (4.59K)' }).click();
    await expect(page.getByRole('img')).toBeVisible();
    await page.goto('http://localhost:8002/');


    // Ensure that it is accessible by guests
    const guestctx1 = await brows.newContext();
    const guestpage1 = await guestctx1.newPage();
    await guestpage1.goto('http://localhost:8002/pages/test_static_server/static/linux.png');
    await expect(guestpage1.getByRole('img')).toBeVisible();
    await guestpage1.goto('http://localhost:8002/');
    await guestctx1.close();


    // Go add the __all_permissions__ permission
    await page.getByRole('link', { name: '󱒕 Modules' }).click();
    await page.getByRole('link', { name: 'test_static_server' }).click();
    await page.getByRole('link', { name: '󰖟 static (fileserver)' }).click();
    await page.getByText('Require Permissions').click();
    await page.getByLabel('__all_permissions__').check();
    await page.getByRole('button', { name: 'Submit' }).click();

    // Ensure it's been added
    await page.getByRole('link', { name: '󰖟 static (fileserver)' }).click();
    await page.getByText('Require Permissions').click();
    await expect(page.getByLabel('__all_permissions__')).toBeChecked();


    // Ensure that it's not accessible without login
    const guestctx2 = await brows.newContext();
    const guestpage2 = await guestctx2.newPage();
    await guestpage2.goto('http://localhost:8002/pages/test_static_server/static/linux.png');
    await expect(guestpage2.locator('h2')).toContainText('Please Log In');
    await guestctx2.close();


    // Move it to /pages/test_static_server/static2
    await page.goto('http://localhost:8002/modules/module/test_static_server');
    await page.getByRole('link', { name: '󰉒 Move' }).click();
    await page.getByLabel('New Name').click();
    await page.getByLabel('New Name').fill('static2');
    await page.getByRole('button', { name: 'Submit' }).click();

    // Check new addr
    await page.goto('http://localhost:8002/pages/test_static_server/static2/linux.png');
    await expect(page.getByRole('img')).toBeVisible();



    // Check old thing no longer accessible,
    // Need new context because of the cache
    const context1 = await brows.newContext();
    const page1 = await context1.newPage();
    await login(page1);
    await page1.goto('http://localhost:8002/pages/test_static_server/static/linux.png');
    await expect(page1.getByRole('heading')).toContainText('Not Found');
    await context1.close();


    await deleteModule(page, 'test_static_server');

    // Disable cache with a new context, check that the old thing is no longer accessible
    const context2 = await brows.newContext();
    const page2 = await context2.newPage();
    await login(page2);
    await page2.goto('http://localhost:8002/pages/test_static_server/static2/linux.png');
    await expect(page2.getByRole('heading')).toContainText('Error');
    await context2.close();


    await brows.close();
    await logout(page);
});