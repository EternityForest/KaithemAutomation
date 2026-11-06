// End-to-end test for the Bluetooth console plugin.
//
// `make dev-run-bluetooth-test` creates two virtual controllers (see
// scripts/virtual-bluetooth-setup.sh) and writes their addresses to
// /tmp/kaithem-bt/env.json.  The test only ever touches those virtual
// controllers: the real hci0 is never scanned, powered, or paired.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';

import { login, sleep } from './util';

const BASE_URL = 'http://localhost:8002';
// Matches the fallback label used by the console for unnamed devices.
const UNKNOWN_DEVICE = 'Unknown device';

interface BluetoothTestEnv {
  host_address: string;
  target_address: string;
  host_path: string;
  target_path: string;
  battery: number;
}

function loadEnv(): BluetoothTestEnv {
  const runtimeDir = process.env.KAITHEM_BT_RUNTIME_DIR ?? '/tmp/kaithem-bt';
  const path = join(runtimeDir, 'env.json');
  let raw: string;
  try {
    raw = readFileSync(path, 'utf8');
  } catch {
    throw new Error(
      `Missing ${path}. Run "make dev-run-bluetooth-test" instead of ` +
        'calling Playwright directly.'
    );
  }
  return JSON.parse(raw) as BluetoothTestEnv;
}

function escapeRegex(value: string): string {
  return value.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

function deviceCard(page: Page, address: string): Locator {
  return page.locator(`[data-testid="bt-device"][data-address="${address}"]`);
}

function controllerCard(page: Page, address: string): Locator {
  return page.locator(
    `[data-testid="bt-controller"][data-address="${address}"]`
  );
}

/** Drive the per-controller scan button until BlueZ reports the wanted state. */
async function setScanning(host: Locator, scanning: boolean): Promise<void> {
  const badge = host.getByTestId('bt-controller-scanning');
  const expected = scanning ? 'Scanning' : 'Not scanning';
  const current = (await badge.textContent())?.trim();
  if (current === expected) {
    return;
  }
  await host.getByTestId('bt-scan').click();
  await expect(badge).toHaveText(expected, { timeout: 30_000 });
}

/**
 * Toggle a Lit-controlled checkbox with a single click.
 *
 * `check()`/`uncheck()` throw when a re-render restores the old value, which
 * happens while the REST call is in flight.  One click plus a retrying
 * assertion converges once the server snapshot arrives.
 */
async function setToggle(box: Locator, checked: boolean): Promise<void> {
  await expect(box).toBeEnabled({ timeout: 30_000 });
  if ((await box.isChecked()) !== checked) {
    await box.click();
  }
  if (checked) {
    await expect(box).toBeChecked();
  } else {
    await expect(box).not.toBeChecked();
  }
}

async function acceptPairingPrompt(page: Page): Promise<void> {
  const prompt = page.getByTestId('bt-prompt');
  const appeared = await prompt
    .waitFor({ state: 'visible', timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  if (!appeared) {
    return;
  }
  await prompt.getByTestId('bt-prompt-accept').click();
  await expect(prompt).toHaveCount(0, { timeout: 20_000 });
}

/** Recover from a run that was interrupted after pairing. */
async function forgetPairingIfPresent(
  page: Page,
  address: string
): Promise<void> {
  const card = deviceCard(page, address);
  const forget = card.getByTestId('bt-forget');
  if (!(await forget.isVisible().catch(() => false))) {
    return;
  }
  page.once('dialog', (dialog) => void dialog.accept());
  await forget.click();
  await expect(card.getByTestId('bt-status-paired')).toHaveCount(0, {
    timeout: 30_000,
  });
}

test('pairs, alerts, auto-connects, and forgets a virtual device', async ({
  page,
  context,
}) => {
  test.setTimeout(480_000);
  page.setDefaultTimeout(60_000);

  const env = loadEnv();
  const targetAddress = env.target_address.toUpperCase();

  await login(page);
  await page.goto(`${BASE_URL}/bluetooth`);

  const host = controllerCard(page, env.host_address);
  await expect(host).toBeVisible({ timeout: 30_000 });
  await expect(host.getByTestId('bt-controller-address')).toHaveText(
    env.host_address
  );

  await setScanning(host, true);

  const target = deviceCard(page, targetAddress);
  await expect(target).toBeVisible({ timeout: 45_000 });

  // A previous interrupted run may have left the target paired and connected.
  await forgetPairingIfPresent(page, targetAddress);

  // Discovery competes with pairing for the controller, so stop it first.
  await setScanning(host, false);

  await expect(target.getByTestId('bt-pair')).toBeVisible({ timeout: 20_000 });
  await target.getByTestId('bt-pair').click();
  await acceptPairingPrompt(page);

  await expect(target.getByTestId('bt-status-paired')).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByTestId('bt-error')).toHaveCount(0);

  // Pairing does not always keep the link up; connect explicitly so BlueZ
  // resolves the battery service and exports org.bluez.Battery1.
  const connected = target.getByTestId('bt-status-connected');
  if (!(await connected.isVisible().catch(() => false))) {
    await target.getByTestId('bt-connect').click();
  }
  await expect(connected).toBeVisible({ timeout: 45_000 });
  await expect(target.getByTestId('bt-battery')).toHaveText(`${env.battery}%`, {
    timeout: 45_000,
  });

  // Alerts must be on before the disconnect.  Auto-connect then brings the
  // device back without any further user interaction.
  const autoConnect = target.getByTestId('bt-auto-connect');
  const alerts = target.getByTestId('bt-alerts');
  await setToggle(autoConnect, true);
  await setToggle(alerts, true);
  // Let the saved configuration reach the supervisor.
  await sleep(1_500);

  const labels = new Set<string>([targetAddress]);
  const uiLabel = (await target.getByTestId('bt-device-name').textContent())
    ?.trim()
    .replaceAll(/\s+/g, ' ');
  if (uiLabel && uiLabel !== UNKNOWN_DEVICE) {
    labels.add(uiLabel);
  }
  const labelPattern = [...labels].map(escapeRegex).join('|');
  const alertText = (outcome: string) =>
    new RegExp(
      `Alarm Bluetooth ${escapeRegex(targetAddress)}: ` +
        `(?:${labelPattern}) disconnected ${outcome}`
    );

  // Observe the system notification feed from a second page; the console page
  // does not render notifications itself.
  const mainPage = await context.newPage();
  await mainPage.goto(`${BASE_URL}/index`);
  const notifications = mainPage.locator('kaithem-notifications');
  await expect(notifications).toBeAttached({ timeout: 30_000 });

  await target.getByTestId('bt-disconnect').click();
  await expect(notifications).toContainText(alertText('is alerting'), {
    timeout: 45_000,
  });

  await expect(connected).toBeVisible({ timeout: 45_000 });
  // A cleared error alert auto-acknowledges after ten seconds.
  await expect(notifications).toContainText(alertText('returned to normal'), {
    timeout: 90_000,
  });

  // With auto-connect off the device must stay disconnected across at least
  // one supervisor tick.
  await setToggle(autoConnect, false);
  await sleep(1_500);
  await target.getByTestId('bt-disconnect').click();
  await expect(connected).toHaveCount(0, { timeout: 30_000 });
  await sleep(7_000);
  await expect(connected).toHaveCount(0);

  await target.getByTestId('bt-connect').click();
  await expect(connected).toBeVisible({ timeout: 45_000 });

  page.once('dialog', (dialog) => void dialog.accept());
  await target.getByTestId('bt-forget').click();
  await expect(target.getByTestId('bt-status-paired')).toHaveCount(0, {
    timeout: 30_000,
  });

  // The device is rediscovered as an unpaired peer, ready to pair again.
  await setScanning(host, true);
  await expect(target).toBeVisible({ timeout: 45_000 });
  await expect(target.getByTestId('bt-pair')).toBeVisible({ timeout: 20_000 });
  await expect(target.getByTestId('bt-status-paired')).toHaveCount(0);
});
