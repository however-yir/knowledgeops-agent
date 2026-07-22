import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";

export interface PdfPageText {
  pageNumber: number;
  text: string;
}

export interface ParsedDocument {
  text: string;
  pages?: PdfPageText[];
}

export async function parsePdf(content: Buffer): Promise<ParsedDocument> {
  if (content.length === 0) {
    throw new Error("corrupt PDF: empty file");
  }
  const loadingTask = pdfjs.getDocument({
    data: new Uint8Array(content),
    useSystemFonts: true
  });
  try {
    const document = await loadingTask.promise;
    const pages: PdfPageText[] = [];
    try {
      for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
        const page = await document.getPage(pageNumber);
        const contentItems = await page.getTextContent();
        const text = contentItems.items
          .map((item) => "str" in item ? item.str : "")
          .join(" ")
          .replace(/[ \t]+/g, " ")
          .trim();
        if (text) {
          pages.push({ pageNumber, text });
        }
        page.cleanup();
      }
    } finally {
      await document.cleanup();
    }
    const text = pages.map((page) => page.text).join("\n\n").trim();
    if (!text) {
      throw new Error("PDF contains no extractable text");
    }
    return { text, pages };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/password|encrypted|incorrect password/i.test(message)) {
      throw new Error("encrypted PDF is not supported");
    }
    if (/no extractable text/i.test(message)) {
      throw new Error("PDF contains no extractable text");
    }
    throw new Error(`corrupt PDF: ${message}`);
  } finally {
    await loadingTask.destroy();
  }
}
