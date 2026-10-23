#!/usr/bin/env python3
"""Unwrap hard-wrapped prose in Markdown files (see AGENTS.md §文档写作约定).

Rules:
- Logical line = paragraph line, heading, table row, list item, or blockquote
  line. A "continuation" is a non-blank line that follows a paragraph/list
  item/blockquote line and is not itself the start of a new block (heading,
  list marker, table row, code fence, blockquote opener). Continuations are
  merged into the line they continue.
- Fenced code blocks (``` / ~~~) are copied verbatim.
- Joining inserts no space when either boundary char is CJK; otherwise one
  space. Trailing spaces before the break are dropped unless they are a
  hard-break (exactly two+ trailing spaces at EOL is treated as intentional:
  the break is kept by emitting a two-space hard break).
- Table rows, headings, and blank lines are emitted unchanged.

Usage: tools/unwrap_md.py [--check] file.md [file.md ...]
  --check  print unified diff, do not write
Exit code: number of files that would change (0 = nothing to do).
"""
import argparse
import difflib
import re
import sys

CJK_IDEO = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")
WIDE_PUNCT = re.compile(
    r"[\u2014\u2018\u2019\u201c\u201d\u2026\u2e80-\u303f\uff01-\uff5d\u3001-\u3011]"
)
OPEN_PUNCT = "（(“「『【《〈"
FENCE = re.compile(r"^(\s*)(```|~~~)")
HEADING = re.compile(r"^#{1,6}\s")
TABLE = re.compile(r"^\s*\|")
BULLET = re.compile(r"^\s*([-*+])\s+")
ORDERED = re.compile(r"^\s*(\d+[.)])\s+")
QUOTE = re.compile(r"^(\s*)>\s?(.*)$")
HRULE = re.compile(r"^\s*(---+|\*\*\*+|___+)\s*$")


def join(prev: str, nxt: str) -> str:
    prev = prev.rstrip()
    nxt = nxt.strip()
    if not prev:
        return nxt
    if not nxt:
        return prev
    a, b = prev[-1], nxt[0]
    no_space = (
        a in OPEN_PUNCT
        or bool(WIDE_PUNCT.match(a))
        or (
            bool(CJK_IDEO.match(a))
            and (bool(CJK_IDEO.match(b)) or bool(WIDE_PUNCT.match(b)))
        )
    )
    return prev + ("" if no_space else " ") + nxt


class Unwrapper:
    def __init__(self):
        self.out: list[str] = []
        self.in_fence = False

    def emit(self, line: str):
        self.out.append(line.rstrip())

    def feed(self, lines: list[str]) -> list[str]:
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            if FENCE.match(line):
                self.in_fence = not self.in_fence
                self.emit(line)
                i += 1
                continue
            if self.in_fence or not line.strip():
                self.emit(line)
                i += 1
                continue
            if HEADING.match(line) or TABLE.match(line) or HRULE.match(line):
                self.emit(line)
                i += 1
                continue
            m = QUOTE.match(line)
            if m:
                block, i = self._collect_quote(lines, i)
                self.out.extend(self._unwrap_quote(block))
                continue
            # paragraph / list-item start: marker line or plain prose
            self._start_logical(line)
            i += 1
            while i < n:
                nxt = lines[i]
                if (
                    not nxt.strip()
                    or self.in_fence
                    or FENCE.match(nxt)
                    or HEADING.match(nxt)
                    or TABLE.match(nxt)
                    or QUOTE.match(nxt)
                    or BULLET.match(nxt)
                    or ORDERED.match(nxt)
                ):
                    break
                if nxt.startswith("    ") and self._is_top_para:
                    # 4-space indent right after a top-level paragraph is a
                    # lazy continuation in markdown too; join it.
                    pass
                self._append_continuation(nxt)
                i += 1
            self._flush()
        return self.out

    # --- logical line buffering ---
    _buf: str = ""
    _pending_break: bool = False
    _is_top_para: bool = False

    def _start_logical(self, line: str):
        self._flush()
        self._is_top_para = not (BULLET.match(line) or ORDERED.match(line))
        self._buf = line.rstrip()
        self._pending_break = line.endswith("  ")  # hard break marker

    def _append_continuation(self, cont: str):
        if self._pending_break:
            self.emit(self._buf + "  ")
            self._buf = cont.strip()
            self._pending_break = cont.endswith("  ")
        else:
            self._buf = join(self._buf, cont)
            self._pending_break = cont.endswith("  ")

    def _flush(self):
        if self._buf:
            self.emit(self._buf + ("  " if self._pending_break else ""))
            self._buf = ""
            self._pending_break = False

    # --- blockquotes: unwrap inner text, keep "> " prefix ---
    def _collect_quote(self, lines, i):
        block = []
        while i < len(lines):
            m = QUOTE.match(lines[i])
            if not m:
                break
            block.append(m.group(2))
            i += 1
        return block, i

    def _unwrap_quote(self, block):
        paras: list[str] = []
        for inner in block:
            if not inner.strip():
                paras.append("")
                continue
            if paras and paras[-1] != "" and not HEADING.match(inner) \
                    and not TABLE.match(inner) and not BULLET.match(inner) \
                    and not ORDERED.match(inner) and not HRULE.match(inner):
                paras[-1] = join(paras[-1], inner)
            else:
                paras.append(inner.rstrip())
        return ["> " + p if p else ">" for p in paras]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    changed = 0
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        lines = src.split("\n")
        trailing_nl = lines and lines[-1] == ""
        if trailing_nl:
            lines.pop()
        out = Unwrapper().feed(lines)
        dst = "\n".join(out) + ("\n" if trailing_nl else "")
        if dst == src:
            continue
        changed += 1
        if args.check:
            sys.stdout.writelines(
                difflib.unified_diff(
                    src.splitlines(keepends=True),
                    dst.splitlines(keepends=True),
                    fromfile=path + " (before)",
                    tofile=path + " (after)",
                )
            )
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(dst)
            print(f"unwrapped: {path}", file=sys.stderr)
    sys.exit(min(changed, 125))


if __name__ == "__main__":
    main()
