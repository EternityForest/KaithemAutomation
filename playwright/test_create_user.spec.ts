import { test, expect } from '@playwright/test';

/* Preconditions:
Guest has view status permission and nothing else
*/


test('test', async ({ page }) => {
    await page.goto('http://localhost:8002/');

    await page.getByLabel('Username:').click();
    await page.getByLabel('Username:').fill('admin');
    await page.getByLabel('Username:').press('Tab');
    await page.getByLabel('Password:').fill('test-admin-password');
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'Users and Groups' }).click();
    await page.getByRole('link', { name: 'Add New User' }).click();
    await page.getByLabel('Username').click();
    await page.getByLabel('Username').fill('test_user');
    await page.getByLabel('Password', { exact: true }).click();
    await page.getByLabel('Password', { exact: true }).fill('1234');
    await page.getByRole('button', { name: 'Submit' }).click();

    // Add the user to guests
    await page.getByRole('link', { name: 'test_user' }).click();
    await page.getByLabel('Guests').check();
    await page.getByRole('button', { name: 'Save Changes' }).click();


    await expect(page.getByRole('main')).toContainText('test_user');
    await page.getByRole('link', { name: 'test_user' }).click();
    await expect(page.locator('h2')).toContainText('test_user');
    await expect(page.getByLabel('Administrators')).not.toBeChecked();
    await expect(page.getByLabel('Guests')).toBeChecked();
    await page.getByRole('button', { name: 'Save Changes' }).click();
    await page.getByRole('button', { name: 'Logout(admin)' }).click();

    await page.getByLabel('Username:').click();
    await page.getByLabel('Username:').fill('test_user');
    await page.getByLabel('Password:').click();
    await page.getByLabel('Password:').fill('1234');
    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
    await expect(page.getByRole('banner')).toContainText('Logout(test_user)');
    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });
    await page.getByRole('link', { name: 'Modules' }).click();

    await expect(page.getByRole('heading')).toContainText('Permission Error');

    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });
    await page.getByRole('link', { name: 'Tools' }).click();

    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });

    await page.getByRole('link', { name: 'System Settings' }).click()
    await expect(page.getByRole('heading')).toContainText('Log In');

    await page.getByRole('link', { name: 'Devices' }).click();
    await expect(page.getByRole('heading')).toContainText('Log In');
    page.once('dialog', dialog => {
        console.log(`Dialog message: ${dialog.message()}`);
        dialog.dismiss().catch(() => { });
    });
    
    
    await page.getByText('Logout(test_user)').click();
    

    await page.goto('http://localhost:8002/login/?go=aHR0cDovL2xvY2FsaG9zdDo4MDAyL2luZGV4');
    await page.getByLabel('Username:').fill('admin');
    await page.getByLabel('Password:').fill('test-admin-password');
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
    await page.getByRole('link', { name: 'Tools' }).click();
    await page.getByRole('link', { name: 'Users and Groups' }).click();
    await page.getByRole('link', { name: 'Delete User' }).click();
    await page.getByLabel('User').click();
    await page.getByLabel('User').fill('test_user');
    await page.getByRole('button', { name: 'Submit' }).click();
    await page.getByRole('button', { name: 'Logout(admin)' }).click();

    await page.getByLabel('Username:').click();
    await page.getByLabel('Username:').fill('test_user');
    await page.getByLabel('Username:').press('Tab');
    await page.getByLabel('Password:').fill('1234');
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
    await expect(page.getByRole('heading')).toContainText('Error');
});