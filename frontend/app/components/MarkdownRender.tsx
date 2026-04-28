/**
 * MarkdownRender — minimal markdown -> HTML for the proposal brief.
 *
 * Handles the subset of markdown the Python proposal renderer actually
 * emits: # h1, ## h2, **bold**, *em*, _em_, "- " lists, paragraphs
 * separated by blank lines. No external dep — keeps the bundle small.
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inlineFormat(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*(.+?)\*/g, "<em>$1</em>");
  out = out.replace(/_(.+?)_/g, "<em>$1</em>");
  return out;
}

function renderMarkdown(md: string): string {
  if (!md) return "";
  const lines = md.split("\n");
  const out: string[] = [];
  let inList = false;
  let para: string[] = [];

  function flushPara() {
    if (para.length) {
      out.push(`<p>${inlineFormat(para.join(" "))}</p>`);
      para = [];
    }
  }

  for (const line of lines) {
    if (line.startsWith("# ")) {
      flushPara();
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      out.push(`<h1>${inlineFormat(line.slice(2))}</h1>`);
    } else if (line.startsWith("## ")) {
      flushPara();
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
      out.push(`<h2>${inlineFormat(line.slice(3))}</h2>`);
    } else if (line.startsWith("- ")) {
      flushPara();
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inlineFormat(line.slice(2))}</li>`);
    } else if (line.trim() === "") {
      flushPara();
      if (inList) {
        out.push("</ul>");
        inList = false;
      }
    } else {
      para.push(line);
    }
  }
  flushPara();
  if (inList) out.push("</ul>");
  return out.join("\n");
}

export function MarkdownRender({ md }: { md: string }) {
  return (
    <div
      className="proposal-md"
      dangerouslySetInnerHTML={{ __html: renderMarkdown(md) }}
    />
  );
}
