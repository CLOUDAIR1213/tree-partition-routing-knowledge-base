import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/chat", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        code: "OK",
        answer: "部署前需要完成变更审核，并保留回滚方案。",
        route: "tech",
        decision_source: "user_hint",
        answerable: true,
        citations: [
          {
            chunk_id: "chunk-tech-12",
            document_id: "doc-tech",
            title: "生产部署规范",
            section: "发布流程",
            page_start: 8,
            page_end: 8,
          },
        ],
        suggested_partitions: [],
        request_id: "req-e2e",
        warning: null,
      }),
    });
  });

  const documentId = "doc_0123456789abcdef01234567";
  await page.route(`**/api/v1/documents/${documentId}/preview*`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        document_id: documentId,
        title: "生产部署规范",
        selected_partition: "tech",
        confirmed_partition: null,
        status: "pending_review",
        chunk_count: 2,
        items: [
          {
            chunk_id: "chunk-tech-1",
            chunk_index: 0,
            title: "发布流程",
            section_path: "部署 > 发布流程",
            page_start: 1,
            page_end: 2,
            preview: "部署前需要完成变更审核，并准备经过验证的回滚方案。",
          },
          {
            chunk_id: "chunk-tech-2",
            chunk_index: 1,
            title: "验证",
            section_path: "部署 > 验证",
            page_start: 3,
            page_end: 3,
            preview: "发布完成后检查核心服务、日志和监控指标。",
          },
        ],
        total: 2,
        limit: 20,
        offset: 0,
        request_id: "req-preview",
      }),
    });
  });
  await page.route(`**/api/v1/documents/${documentId}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        document_id: documentId,
        original_filename: "production-deployment.md",
        title: "生产部署规范",
        selected_partition: "tech",
        confirmed_partition: null,
        status: "pending_review",
        chunk_count: 2,
        created_at: "2026-09-01T08:00:00Z",
        updated_at: "2026-09-01T08:00:00Z",
        mime_type: "text/markdown",
        size_bytes: 4096,
        reviewed_at: null,
        review_note: null,
        error_code: null,
        error_message: null,
        request_id: "req-detail",
      }),
    });
  });
});

test("chat layout stays usable and produces a viewport screenshot", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "从企业知识开始提问" })).toBeVisible();
  await expect(page.getByRole("link", { name: "上传知识" })).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);

  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath(`chat-${testInfo.project.name}.png`),
  });
});

test("question flow and upload navigation work", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("radio", { name: "技术" }).click();
  await page.getByLabel("输入知识库问题").fill("生产环境如何部署？");
  await page.getByRole("button", { name: "发送问题" }).click();
  await expect(page.getByText("部署前需要完成变更审核，并保留回滚方案。")).toBeVisible();
  await expect(page.getByText("生产部署规范")).toBeVisible();

  await page.getByRole("link", { name: "上传知识" }).click();
  await expect(page).toHaveURL(/\/knowledge\/upload$/);
  await expect(page.getByRole("heading", { name: "上传知识库文档" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
});

test("upload and review layouts remain responsive", async ({ page }, testInfo) => {
  await page.goto("/knowledge/upload");
  await expect(page.getByRole("heading", { name: "上传知识库文档" })).toBeVisible();
  await expect(page.getByRole("button", { name: "上传并解析" })).toBeDisabled();
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath(`upload-${testInfo.project.name}.png`),
  });

  await page.goto("/knowledge/review/doc_0123456789abcdef01234567");
  await expect(page.getByRole("heading", { name: "生产部署规范" })).toBeVisible();
  await expect(page.getByText("部署前需要完成变更审核，并准备经过验证的回滚方案。")).toBeVisible();
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath(`review-${testInfo.project.name}.png`),
  });
});
