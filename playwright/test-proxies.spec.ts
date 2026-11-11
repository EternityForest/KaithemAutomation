import { test, expect } from '@playwright/test';
import { BASE, login, logout, makeModule, deleteModule } from './util';

/* End to end test for the CorePluginProxies proxy management framework.
 *
 * A proxy resource is created pointing at the main Kaithem page and
 * requiring system_admin.  We check that it shows up on the module page
 * and the apps page (linking straight to its subdomain), that the admin
 * can load it, that a guest is redirected to the login page, and that
 * deleting the resource makes it disappear again.
 */

const MODULE = 'test_proxies';
const RESOURCE = 'p1';
const SUBDOMAIN = 'testproxy';
const SUBDOMAIN_ORIGIN = `http://${SUBDOMAIN}.localhost:8002`;

test('proxy resource lifecycle', async ({ page, browser }) => {
    test.setTimeout(2_400_000);

    await login(page);
    await makeModule(page, MODULE);

    // Create the proxy resource through the schema based add dialog.
    await page.getByTestId('add-resource-button').click();
    await page.getByTestId('add-proxy').click();
    await page.getByLabel('Resource Name').click();
    await page.getByLabel('Resource Name').fill(RESOURCE);

    // The JSON editor applies its default asynchronously; wait for that
    // before replacing the value with our proxy configuration.
    await page.waitForFunction(() => {
        const editor = (globalThis as any).editor;
        return editor && editor.getValue().subdomain === 'example';
    });
    await page.evaluate((subdomain: string) => {
        (globalThis as any).editor.setValue({
            subdomain,
            target: 'http://127.0.0.1:8002/',
            title: 'Test Proxy',
            permissions: ['system_admin'],
        });
    }, SUBDOMAIN);
    await page.getByRole('button', { name: 'Save' }).click();

    // The proxy shows up on the module page.
    await expect(page.getByTestId(`proxy-blurb-${RESOURCE}`)).toBeVisible();

    // And on the apps page, linking straight to its subdomain.
    await page.goto(`${BASE}/apps`);
    const appEntry = page.getByTestId(`app-proxy_${SUBDOMAIN}`);
    await expect(appEntry).toBeVisible();
    await expect(appEntry.getByRole('link')).toHaveAttribute(
        'href',
        `//${SUBDOMAIN}.localhost:8002/`
    );

    // Logged in, the proxy loads the backend (the main page).  The auth
    // cookie is host-only for localhost, so grant it for the subdomain.
    const cookies = await page.context().cookies(`${BASE}/`);
    const auth = cookies.find((cookie) => cookie.name === 'kaithem_auth');
    expect(auth).toBeTruthy();
    await page.context().addCookies([
        {
            name: 'kaithem_auth',
            value: auth!.value,
            url: `${SUBDOMAIN_ORIGIN}/`,
        },
    ]);
    await page.goto(`${SUBDOMAIN_ORIGIN}/`);
    await expect(page.getByRole('link', { name: 'Modules' })).toBeVisible();

    // Without login the proxy redirects to the login page.
    const guestContext = await browser.newContext();
    const guestPage = await guestContext.newPage();
    await guestPage.goto(`${SUBDOMAIN_ORIGIN}/`);
    await expect(
        guestPage.getByRole('heading', { name: 'Please Log In' })
    ).toBeVisible();
    await guestContext.close();

    // Delete the resource; the proxy goes away.
    await page.goto(`${BASE}/modules/module/${MODULE}`);
    await page.getByTestId('delete-resource-button').click();
    await page.getByRole('button', { name: 'Submit' }).click();

    await expect(page.getByTestId(`proxy-blurb-${RESOURCE}`)).not.toBeVisible();

    await page.goto(`${BASE}/apps`);
    await expect(page.getByTestId(`app-proxy_${SUBDOMAIN}`)).not.toBeVisible();

    await deleteModule(page, MODULE);
    await logout(page);
});
