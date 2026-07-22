import PDFDocument from "pdfkit";
import { describe, expect, it } from "vitest";

import { parsePdf } from "./pdf.parser.js";

describe("parsePdf", () => {
  it("extracts text and page numbers with a maintained PDF parser", async () => {
    const document = await createPdf(["First page policy", "Second page evidence"]);

    const parsed = await parsePdf(document);

    expect(parsed.text).toContain("First page policy");
    expect(parsed.text).toContain("Second page evidence");
    expect(parsed.pages).toEqual([
      { pageNumber: 1, text: "First page policy" },
      { pageNumber: 2, text: "Second page evidence" }
    ]);
  });

  it("rejects malformed PDF bytes", async () => {
    await expect(parsePdf(Buffer.from("%PDF-1.7\nnot a real document"))).rejects.toThrow("corrupt PDF");
  });

  it("rejects PDFs without extractable text", async () => {
    const document = await createPdf([]);

    await expect(parsePdf(document)).rejects.toThrow("PDF contains no extractable text");
  });
});

function createPdf(pages: string[]): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const document = new PDFDocument({ autoFirstPage: false, compress: false });
    const chunks: Buffer[] = [];
    document.on("data", (chunk: Buffer) => chunks.push(chunk));
    document.on("error", reject);
    document.on("end", () => resolve(Buffer.concat(chunks)));
    if (pages.length === 0) {
      document.addPage();
    } else {
      for (const text of pages) {
        document.addPage().fontSize(12).text(text);
      }
    }
    document.end();
  });
}
