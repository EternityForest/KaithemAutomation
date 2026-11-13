// End-to-end test for the CorePluginPydanticConversation chat feature.
//
// The testing server points OpenRouter at a loopback mock that echoes
// whatever it is sent (see kaithem/src/tests/ai_mock.py), so this test
// exercises the real WebSocket chat UI without ever reaching a paid
// provider.  It covers resource creation, the "Open Chat" link, sending
// a message, the token/cost display, the show/hide thoughts toggle, the
// mobile thread sidebar, and that deleting the module removes the
// conversation.

import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

import { BASE, login, makeModule, deleteModule } from './util';

const MODULE = 'TestConversation';
const RESOURCE = 'chat1';

/** Create a conversation resource through the schema based dialog. */
async function createConversation(page: Page): Promise<void> {
  await page.goto(`${BASE}/modules/module/${MODULE}`);
  await page.getByTestId('add-resource-button').click();
  await page.getByTestId('add-conversation').click();
  await page.getByLabel('Resource Name').fill(RESOURCE);
  await page.getByLabel('Conversation Title').fill('Test Chat');
  await page.getByRole('button', { name: 'Submit' }).click();
}

/** The conversation uuid is the ?uuid= query parameter of the chat page. */
function conversationId(page: Page): string {
  const id = new URL(page.url()).searchParams.get('uuid');
  expect(id).toBeTruthy();
  return id as string;
}

test('conversation chat lifecycle', async ({ page }) => {
  test.setTimeout(120_000);

  await login(page);
  await makeModule(page, MODULE);
  await createConversation(page);

  // The blurb on the module page links to the chat UI.
  await page.goto(`${BASE}/modules/module/${MODULE}`);
  await expect(
    page.getByTestId(`conversation-blurb-${RESOURCE}`)
  ).toBeVisible();
  await page.getByTestId('open-conversation').click();

  const uuid = conversationId(page);

  // The page auto-creates an initial thread, which enables the composer.
  const input = page.getByTestId('chat-input');
  await expect(input).toBeEnabled({ timeout: 30_000 });

  // Send a message and wait for the echoed reply over the WebSocket.
  await input.fill('Hello there');
  await page.getByTestId('chat-send').click();
  const messages = page.getByTestId('chat-messages');
  await expect(messages).toContainText('Echo: Hello there', {
    timeout: 30_000
  });

  // The assistant message shows token counts and a cost.
  const usage = page.getByTestId('chat-usage').first();
  await expect(usage).toBeVisible();
  await expect(usage).toContainText('in');
  await expect(usage).toContainText('out');
  await expect(usage).toContainText('$');

  // Thoughts are hidden by default and can be revealed.
  const thoughts = page.getByTestId('chat-thoughts-toggle').first();
  await expect(thoughts).toBeVisible();
  await expect(thoughts).toContainText('Show thoughts');
  await thoughts.click();
  await expect(thoughts).toContainText('Hide thoughts');
  await expect(page.locator('.chat-thoughts-body').first()).toContainText(
    'Considering:'
  );

  // On a phone the thread list is an off-canvas drawer opened from the
  // header, and picking a thread closes it again.
  await page.setViewportSize({ width: 390, height: 780 });
  const sidebar = page.getByTestId('chat-sidebar');
  const menu = page.getByTestId('chat-menu');
  await expect(menu).toBeVisible();
  await expect(sidebar).not.toHaveClass(/open/);
  await menu.click();
  await expect(sidebar).toHaveClass(/open/);
  await page.getByTestId('chat-thread').first().click();
  await expect(sidebar).not.toHaveClass(/open/);

  // Deleting the module deletes the conversation and its history.
  await deleteModule(page, MODULE);
  const response = await page.request.get(`${BASE}/conversations/${uuid}`);
  expect(response.status()).toBe(404);
});
