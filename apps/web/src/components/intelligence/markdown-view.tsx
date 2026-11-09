import { Fragment } from "react";

/**
 * Renders the Markdown produced by the report template (services/api/app/reports/render.py):
 * headings, paragraphs, block quotes, bullet lists, pipe tables and **bold**. Anything
 * else is shown as plain text. No HTML is interpreted, so nothing can be injected.
 */
export function MarkdownView({ md, skipTitle = true }: { md: string; skipTitle?: boolean }) {
  const lines = md.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  let section = "Report";
  let tables = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i++;
      continue;
    }
    if (line.startsWith("# ")) {
      if (!skipTitle) blocks.push(<h1 key={key++} className="text-lg font-semibold">{inline(line.slice(2))}</h1>);
      i++;
      continue;
    }
    if (line.startsWith("## ")) {
      section = line.slice(3).replaceAll("**", "");
      blocks.push(
        <h2 key={key++} className="mt-6 border-b border-border pb-1 text-sm font-semibold text-foreground first:mt-0">
          {inline(line.slice(3))}
        </h2>,
      );
      i++;
      continue;
    }
    if (line.startsWith("> ")) {
      blocks.push(
        <blockquote key={key++} className="rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-xs">
          {inline(line.slice(2))}
        </blockquote>,
      );
      i++;
      continue;
    }
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) items.push(lines[i++].slice(2));
      blocks.push(
        <ul key={key++} className="list-disc space-y-1 pl-5 text-[13px]">
          {items.map((t, j) => (
            <li key={j}>{inline(t)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(lines[i++].slice(1, -1).split("|").map((c) => c.trim()));
      }
      const [head, sep, ...body] = rows;
      const right = (sep ?? []).map((s) => s.endsWith(":"));
      blocks.push(
        <div
          key={key++}
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label={`${section} table ${++tables}`}
        >
          <table className="w-full text-xs">
            <thead className="text-[11px] text-muted-foreground">
              <tr className="border-b border-border">
                {head.map((h, j) => (
                  <th key={j} className={`py-1.5 pr-3 font-normal ${right[j] ? "text-right" : "text-left"}`}>
                    {inline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="metric">
              {body.map((r, k) => (
                <tr key={k} className="border-b border-border/60 last:border-0">
                  {r.map((c, j) => (
                    <td key={j} className={`py-1.5 pr-3 ${right[j] ? "text-right" : ""}`}>
                      {inline(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    // Always consume at least one line, so unexpected input cannot stall the loop.
    const para: string[] = [lines[i++]];
    while (i < lines.length && lines[i].trim() !== "" && !/^(# |## |> |- |\|)/.test(lines[i])) para.push(lines[i++]);
    blocks.push(
      <p key={key++} className="text-[13px] text-muted-foreground">
        {inline(para.join(" "))}
      </p>,
    );
  }
  return <div className="space-y-3">{blocks}</div>;
}

function inline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? (
      <strong key={i} className="font-semibold text-foreground">
        {p.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{p}</Fragment>
    ),
  );
}
