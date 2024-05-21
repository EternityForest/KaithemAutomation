import { Page } from '@playwright/test';

async function login(page: Page) {
    await page.goto('http://localhost:8002/');
    await page.getByRole('link', { name: 'Login' }).click();
    await page.getByLabel('Username:').click();
    await page.getByLabel('Username:').fill('admin');
    await page.getByLabel('Username:').press('Tab');
    await page.getByLabel('Password:').fill('test-admin-password');
    await page.getByRole('button', { name: 'Login as Registered User' }).click();
}

async function logout(page: Page) {
    await page.getByRole('button', { name: 'Logout(admin)' }).click();
}

async function deleteModuleIfExist(page: Page, name: string) {
    await page.getByRole('link', { name: 'Modules' }).click();

    if (await page.getByText(name).isVisible()) {
        await page.getByRole('link', { name: 'Delete' }).click();
        await page.getByLabel('Name').fill(name);
        await page.getByRole('button', { name: 'Submit' }).click();
    }
}

async function makeModule(page: Page, name: string) {
    await deleteModuleIfExist(page, name);
    await page.getByRole('link', { name: 'Modules' }).click();

    await page.getByRole('link', { name: 'Add' }).click();

    await page.getByLabel('Name of New Module').click();
    await page.getByLabel('Name of New Module').fill(name);
    await page.getByRole('button', { name: 'Submit' }).click();
}

async function deleteModule(page: Page, name: string) {
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: 'Delete' }).click();
    await page.getByLabel('Name').click();
    await page.getByLabel('Name').fill(name);
    await page.getByRole('button', { name: 'Submit' }).click();
}

async function makeTagPoint(page: Page, module: string, name: string) {
    
    if (name[0] == '/') {
        name = name.substring(1);
    }
    
    await page.getByRole('link', { name: 'Modules' }).click();
    await page.getByRole('link', { name: module }).click();
    await page.getByRole('link', { name: 'Tagpoint' }).click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill(name);
    await page.getByLabel('Tag Point Name').click();
    await page.getByLabel('Tag Point Name').fill(name);
    await page.getByLabel('Default Value').click();
    await page.getByLabel('Default Value').fill('0');
    await page.getByRole('button', { name: 'Submit' }).click();
}

export { login, logout, makeModule, deleteModule, makeTagPoint};