// End-to-end test for the text editor's DAP debugger sidebar.
//
// The mock debug adapter (kaithem/src/tests/dap_mock.py, started by
// testing_server.py) speaks raw DAP over a websocket.  It pretends to run
// a loop that calls a function which increments a global and copies it
// into a local, serving the pseudocode only through the DAP ``source``
// request and pointing one frame at a real file outside the workspace.

import { test, expect, Page } from '@playwright/test';
import { BASE, login, makeModule, deleteModule } from './util.ts';

const MOD = 'test_text_editor_dap';

// The mock's fixed port (see DEFAULT_DAP_MOCK_PORT in dap_mock.py).  The
// Playwright container shares the host network namespace but not
// /dev/shm, so both sides agree on this port instead of a file.
const DAP_PORT = process.env.KAITHEM_TEST_DAP_PORT || '8003';
const DAP_URL = `ws://localhost:${DAP_PORT}`;

// Constants that mirror dap_mock.py.
const PSEUDOCODE_NAME = 'pseudocode.dap';
const PSEUDOCODE_MARKER = 'global counter = 0';
const DISK_PATH = '/dev/shm/kaithem_test_env/dap_disk_source.txt';
const DISK_MARKER = 'A real file outside the editor workspace.';

// A file with several lines so a breakpoint can be set on line 2.
const FILE_CONTENT = 'alpha\nbravo\ncharlie\ndelta\n';

// Workspace path discovered from the /edit redirect in beforeEach.
let WS = '';

async function uploadFileResource(
  page: Page,
  module: string,
  dir: string,
  name: string,
  content: string
) {
  return page.evaluate(
    async ({ module, dir, name, content }) => {
      const fd = new FormData();
      fd.append('dir', dir);
      fd.append('name', name);
      fd.append('file', new File([content], name, { type: 'text/plain' }));
      const r = await fetch(
        '/modules/module/' +
          encodeURIComponent(module) +
          '/uploadfileresourcetarget',
        { method: 'POST', body: fd }
      );
      return { status: r.status, text: await r.text() };
    },
    { module, dir, name, content }
  );
}

async function createFileViaApi(
  page: Page,
  workspace: string,
  path: string,
  content: string
) {
  return page.evaluate(
    async ({ workspace, path, content }) => {
      const fd = new FormData();
      fd.append('workspace', workspace);
      fd.append('path', path);
      fd.append('content', content);
      const r = await fetch('/text-editor-plugin/api/write', {
        method: 'POST',
        body: fd,
      });
      return { status: r.status, text: await r.text() };
    },
    { workspace, path, content }
  );
}

// The /edit route redirects to the editor with the detected workspace in
// the URL, so opening any file tells us the workspace the editor uses.
async function discoverWorkspace(
  page: Page,
  module: string,
  resource: string
) {
  await page.goto(
    `${BASE}/text-editor-plugin/edit?module=` +
      encodeURIComponent(module) +
      '&resource=' +
      encodeURIComponent(resource)
  );
  await page.waitForTimeout(2000);
  const url = new URL(page.url());
  return url.searchParams.get('workspace') || '';
}

// Open the editor with the debugger enabled and wait for it to connect.
async function openDebugEditor(page: Page) {
  await page.goto(
    `${BASE}/text-editor-plugin/edit?module=${encodeURIComponent(MOD)}` +
      `&resource=${encodeURIComponent('files/hello.txt')}` +
      `&dap=${encodeURIComponent(DAP_URL)}`
  );
  const host = page.locator('text-editor-page');
  await expect(host.getByTestId('debugger')).toBeVisible();
  await expect(host.getByTestId('dap-badge')).toHaveText('connected');
  return host;
}

async function activeTabInfo(page: Page) {
  return page.evaluate(() => {
    const h = document.querySelector('text-editor-page') as any;
    const tab = h?.tabs?.find((t: any) => t.path === h.activeTab);
    return {
      path: tab?.path ?? null,
      kind: tab?.kind ?? null,
      readonly: tab?.readonly ?? null,
      content: tab?.content ?? null,
    };
  });
}

// Opening a source from a stack frame is asynchronous, so wait for the
// tab to become active before reading it.
async function waitForActiveTab(page: Page, path: string) {
  await expect.poll(async () => (await activeTabInfo(page)).path).toBe(path);
  return activeTabInfo(page);
}

// Click the breakpoint gutter at the vertical position of a 0-based line.
async function toggleBreakpointAtLine(
  page: Page,
  editor: ReturnType<Page['locator']>,
  lineIndex: number
) {
  const lineBox = await editor.locator('.cm-line').nth(lineIndex).boundingBox();
  const gutterBox = await editor
    .locator('.cm-breakpoint-gutter')
    .boundingBox();
  expect(lineBox).not.toBeNull();
  expect(gutterBox).not.toBeNull();
  await page.mouse.click(
    gutterBox!.x + gutterBox!.width / 2,
    lineBox!.y + lineBox!.height / 2
  );
}

test.describe('Text Editor DAP debugger', () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);
    await makeModule(page, MOD);
    await page.goto(`${BASE}/index`);
    await uploadFileResource(page, MOD, 'files', 'hello.txt', 'Hello world\n');
    WS = await discoverWorkspace(page, MOD, 'files/hello.txt');
    await createFileViaApi(page, WS, 'hello.txt', FILE_CONTENT);
  });

  test.afterEach(async ({ page }) => {
    await deleteModule(page, MOD);
  });

  test('sidebar lists breakpoints set in the editor', async ({ page }) => {
    const host = await openDebugEditor(page);
    const editor = host.locator('[data-testid="cm-hello.txt"]');
    await expect(editor).toBeVisible();
    await expect(host.getByTestId('debugger')).toContainText(
      'No breakpoints'
    );

    await toggleBreakpointAtLine(page, editor, 1);

    const breakpoint = host.locator('[data-testid="dap-breakpoint"]');
    await expect(breakpoint).toHaveText('hello.txt:2');
  });

  test('run shows a call stack per thread and jumps to sources', async ({
    page,
  }) => {
    const host = await openDebugEditor(page);
    await expect(host.getByTestId('debugger')).toContainText('Not stopped');

    await host.getByTestId('dap-run').click();

    // Two threads, two frames each.
    await expect(host.locator('[data-testid="dap-frame"]')).toHaveCount(4);
    await expect(host.locator('.debug-thread')).toHaveText([
      'main',
      'worker',
    ]);

    // The worker frame lives in a real file outside the workspace.
    await host
      .locator('[data-testid="dap-frame"]', { hasText: 'dap_disk_source.txt' })
      .click();
    const diskTab = await waitForActiveTab(page, DISK_PATH);
    expect(diskTab.path).toBe(DISK_PATH);
    expect(diskTab.kind).toBe('disk');
    expect(diskTab.readonly).toBe(true);
    expect(diskTab.content).toContain(DISK_MARKER);

    // A frame in the virtual source served only through DAP.
    await host
      .locator('[data-testid="dap-frame"]', { hasText: PSEUDOCODE_NAME })
      .first()
      .click();
    const virtualTab = await waitForActiveTab(page, PSEUDOCODE_NAME);
    expect(virtualTab.path).toBe(PSEUDOCODE_NAME);
    expect(virtualTab.kind).toBe('virtual');
    expect(virtualTab.readonly).toBe(true);
    expect(virtualTab.content).toContain(PSEUDOCODE_MARKER);
  });

  test('step controls advance and the console recalls history', async ({
    page,
  }) => {
    const host = await openDebugEditor(page);
    await host.getByTestId('dap-run').click();
    await expect(host.locator('[data-testid="dap-frame"]')).toHaveCount(4);

    const output = host.getByTestId('dap-console-output');
    const input = host.getByTestId('dap-console-input');
    await expect(output).toContainText('counter = 1');

    // Evaluate the counter the mock reports.
    await input.fill('counter');
    await input.press('Enter');
    await expect(
      output.locator('.console-output').filter({ hasText: /^1$/ })
    ).toHaveCount(1);

    // A step advances the loop and reports a new counter.
    await host.getByTestId('dap-step-over').click();
    await expect(output).toContainText('counter = 2');
    await input.fill('counter + 0');
    await input.press('Enter');
    await expect(output).toContainText('<mock: counter + 0>');

    // Up arrow recalls previous console lines, newest first; down arrow
    // returns through them and finally restores the empty draft.
    await input.press('ArrowUp');
    await expect(input).toHaveValue('counter + 0');
    await input.press('ArrowUp');
    await expect(input).toHaveValue('counter');
    await input.press('ArrowDown');
    await expect(input).toHaveValue('counter + 0');
    await input.press('ArrowDown');
    await expect(input).toHaveValue('');
  });

  test('reconnects after the socket drops and can run again', async ({
    page,
  }) => {
    const host = await openDebugEditor(page);

    // Simulate the connection dropping: the badge flips to disconnected
    // and a reconnect control appears.
    await page.evaluate(() => {
      const h = document.querySelector('text-editor-page') as any;
      h._dap.disconnect();
    });
    await expect(host.getByTestId('dap-badge')).toHaveText('disconnected');
    const reconnect = host.getByTestId('dap-reconnect');
    await expect(reconnect).toBeVisible();

    // Reconnecting opens a fresh session that can run to a stop again.
    await reconnect.click();
    await expect(host.getByTestId('dap-badge')).toHaveText('connected');
    await expect(host.getByTestId('dap-reconnect')).toHaveCount(0);
    await host.getByTestId('dap-run').click();
    await expect(host.locator('[data-testid="dap-frame"]')).toHaveCount(4);
  });

  test('a frame in the workspace reuses the relative tab and breakpoints', async ({
    page,
  }) => {
    const host = await openDebugEditor(page);
    const editor = host.locator('[data-testid="cm-hello.txt"]');
    await expect(editor).toBeVisible();

    await toggleBreakpointAtLine(page, editor, 1);
    await expect(host.locator('[data-testid="dap-breakpoint"]')).toHaveCount(1);

    // A stack frame can report the same file by absolute path.  Opening it
    // must reuse the existing workspace tab instead of opening a second,
    // read-only one, and must not duplicate the breakpoint.
    await page.evaluate((abs) => {
      const h = document.querySelector('text-editor-page') as any;
      return h._openDiskFile(abs, 2);
    }, `${WS}/hello.txt`);

    await expect
      .poll(() =>
        page.evaluate(
          () => (document.querySelector('text-editor-page') as any).tabs.length
        )
      )
      .toBe(1);
    const tab = await activeTabInfo(page);
    expect(tab.path).toBe('hello.txt');
    expect(tab.kind).toBe('workspace');
    expect(tab.readonly).toBe(false);
    await expect(host.locator('[data-testid="dap-breakpoint"]')).toHaveCount(1);
    await expect(host.locator('[data-testid="dap-breakpoint"]')).toHaveText(
      'hello.txt:2'
    );
  });
});
