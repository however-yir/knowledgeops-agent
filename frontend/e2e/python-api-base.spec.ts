import { expect, test } from '@playwright/test';

const apiKey = process.env.E2E_API_KEY ?? 'local-demo-api-key';
const tenantId = process.env.E2E_TENANT_ID ?? 'public';

test('Vue uses the Python canonical API through the switchable /api upstream', async ({ page }) => {
  await page.goto('/');

  await page.getByPlaceholder('输入 API Key（生产建议短时使用）').fill(apiKey);
  await page.getByPlaceholder('public').fill(tenantId);
  const tokenResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/auth/token') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '换取 JWT', exact: true }).click();
  await expect((await tokenResponse).ok()).toBeTruthy();
  await expect(page.getByRole('button', { name: '刷新', exact: true })).toBeEnabled();

  const question = 'frontend canonical API smoke';
  await page.getByPlaceholder('输入问题，Enter 发送，Shift + Enter 换行').fill(question);
  const streamResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/ai/react/chat/stream') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect((await streamResponse).ok()).toBeTruthy();
  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByText('KnowledgeOps Python', { exact: false })).toBeVisible();
});
