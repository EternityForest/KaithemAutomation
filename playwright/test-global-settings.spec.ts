import { test, expect } from '@playwright/test';
import { login, logout, deleteModule } from './util';

test('test', async ({ page }) => {
    await login(page);


   // TODO this is now just a placeholder
    await logout(page);
});