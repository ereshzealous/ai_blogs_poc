"""Publication QA: no local filesystem path, machine name or personal address may reach a published artifact.

A chapter's Markdown, HTML, PDF, SVG, JSON, text and log outputs are scanned for paths that only exist on the machine
that built them: file:// URLs, home directories (macOS, Linux, Windows), temporary and build directories, and any
absolute path the caller names (the repository root, a scratchpad). Since 5.3 they are also scanned for the build
machine's name (the junit hostname attribute, mDNS names ending in .local) and personal e-mail addresses, and since
5.3.1 for the author's folder layout written relative to home (a tilde before Documents, Desktop, Dev and the like). A
named path that does not exist is an error (exit 2), never a clean result. `--relative` also reports
relative links in Markdown and HTML, which lead nowhere once a page is published.  PDFs are scanned after inflating their Flate streams, because
Chrome writes link annotations and object streams compressed: a plain-text scan of a PDF misses exactly the file:// links
that print-to-PDF produces from relative hrefs.

Web links are never findings: a path segment that belongs to an http(s) URL (https://host/home/x/, https://host/tmp/)
is skipped by the lookbehind on every rule, and nothing here rewrites a file.

    from evidence_kit.publication import local_path_findings
    findings = local_path_findings(paths, root, forbid=[repo_root])          # [] when clean

    python -m evidence_kit.publication <file-or-dir> … [--root DIR] [--forbid ABS_PATH] …   # exit 1 on findings
"""
from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path
from typing import Iterable

# A path segment glued to a word, a dot, a colon, a slash, or a base64/URL character is part of something else (a URL
# path, a domain, a data: payload); a local absolute path starts after whitespace, a quote, a bracket or line start.
_START = r"(?<![\w.:/+=%~-])"

RULES: list[tuple[str, str]] = [
    ("file URL", r"\bfile:/{1,3}(?=[^\s\"'<>)\]`/])[^\s\"'<>)\]`]+"),   # a path must follow: prose naming `file://` is not a leak
    ("macOS home directory", _START + r"/Users/[A-Za-z0-9._-]+/"),
    ("Linux home directory", _START + r"/home/[A-Za-z0-9._-]+/"),
    ("Windows home directory", r"\b[A-Za-z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/)[^\\/\s\"'<>]+"),
    ("macOS temporary directory", _START + r"/(?:private/)?var/folders/[\w.-]+/"),
    ("temporary directory", _START + r"/(?:private/)?tmp/[\w.-]+"),
    ("Windows temporary directory", r"(?i)\\AppData\\Local\\Temp\\"),
    ("mounted volume", _START + r"/Volu" r"mes/[^/\s\"'<>]+/"),   # split, so this file scans clean
]

# Identity: a machine name or a personal address in a published file (5.3). Reserved test domains, noreply and git@
# remotes are not personal; Python's `threading.local()` and `~/.local/` are not host names.
_EMAIL_SAFE_DOMAIN = r"(?:[\w-]+\.)*(?:example|test|invalid|localhost)\b|(?:[\w-]+\.)*no-?reply\."

RULES += [
    ("hostname attribute", r'\bhostname="(?!localhost"|<[^"<>]+>"|&lt;[^"&<>]+&gt;")[^"\s]+"'),   # <host> is a declared placeholder
    # the author's folder layout written relative to home; ~/.local, ~/.config and ~/your-clone are not findings
    ("home-relative workspace path", r"(?<![\w/.~-])~/(?:Documents|Desktop|Downloads|Library|Dev|Developer|Projects|Code|"
                                     r"code|src|work|workspace|repos?|git)/[^\s\"'<>)\]`]*"),
    ("mDNS host name", r"(?<![\w.-])[A-Za-z0-9][A-Za-z0-9-]*\.local(?![\w.(-])"),
    # every domain label carries a letter and the top-level domain is letters only, so fact keys (cells.C@500.unsafe)
    # and versioned ids (agent.x@1.3.0, pkg@5.3.0) are not addresses
    # the local part's letter-or-digit condition sits in a lookahead, not between two `*` runs: on a long base64 line the
    # nested form backtracked quadratically (5.3.1)
    ("e-mail address", r"(?<![\w.+-])(?!(?:no-?reply|git)@)(?=[\w.+-]*?[A-Za-z0-9])[\w.+-]+@(?!" + _EMAIL_SAFE_DOMAIN + r")"
                       r"(?:(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}\b"),
]

SUFFIXES = {".md", ".html", ".htm", ".pdf", ".svg", ".json", ".jsonl", ".txt", ".csv", ".xml", ".yaml", ".yml", ".toml", ".log"}


def _pdf_text(raw: bytes) -> str:
    """The PDF's bytes as text plus every Flate stream inflated (unreadable streams are skipped, not guessed)."""
    parts = [raw.decode("latin-1")]
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        try:
            parts.append(zlib.decompressobj().decompress(raw[start:end]).decode("latin-1"))
        except zlib.error:
            continue
    return "\n".join(parts)


def _text(p: Path) -> str:
    raw = p.read_bytes()
    return _pdf_text(raw) if p.suffix.lower() == ".pdf" else raw.decode("utf-8", errors="replace")


def expand(paths: Iterable[Path]) -> list[Path]:
    """Files under the given files and directories whose suffix is a publication format (sorted, de-duplicated)."""
    out: set[Path] = set()
    for p in map(Path, paths):
        if p.is_dir():
            out.update(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUFFIXES)
        elif p.is_file():
            out.add(p)
    return sorted(out)


def local_path_findings(paths: Iterable[Path], root: Path, forbid: Iterable[str | Path] = (),
                        allow: Iterable[str] = ()) -> list[dict]:
    """Findings {file, line, kind, match} for every local path in the files under `paths`.

    `forbid` adds absolute paths that must never appear (the repository root, a scratchpad, the home directory); each is
    matched literally.  `allow` are regexes for matches that are intended (a document that explains the rule with a
    made-up example path); a finding that matches one is not reported."""
    rules = [(k, re.compile(r)) for k, r in RULES]
    rules += [(f"absolute path {f}", re.compile(re.escape(str(f).rstrip("/")) + r"(?=[/\\\s\"'<>]|$)")) for f in forbid if str(f).strip("/")]
    allow_rx = [re.compile(a) for a in allow]
    root = Path(root).resolve()
    out = []
    for p in expand(paths):
        try:
            text = _text(p)
        except OSError:
            continue
        rel = _rel(p, root)
        for i, line in enumerate(text.splitlines(), 1):
            seen = set()
            for kind, rx in rules:
                for m in rx.finditer(line):
                    if m.start() in seen or any(a.search(m.group(0)) for a in allow_rx):
                        continue
                    seen.add(m.start())
                    out.append({"file": rel, "line": i, "kind": kind, "match": m.group(0)[:100]})
    return out


_MD_LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\(\s*<?([^)\s>]+)")
_HTML_LINK = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"']+)["']""", re.I)
_ABSOLUTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#|//)", re.I)


def _rel(p: Path, root: Path) -> str:
    rp, rr = p.resolve(), Path(root).resolve()
    return rp.relative_to(rr).as_posix() if rp.is_relative_to(rr) else p.name


def relative_link_findings(paths: Iterable[Path], root: Path) -> list[dict]:
    """Links (not images) in Markdown and HTML that point at a relative path: on a published page they lead nowhere.
    Images are left alone, because a Medium paste source refers to the images it uploads by relative path."""
    out = []
    for p in expand(paths):
        if p.suffix.lower() not in {".md", ".html", ".htm"}:
            continue
        for i, line in enumerate(_text(p).splitlines(), 1):
            for rx in (_MD_LINK, _HTML_LINK):
                for m in rx.finditer(line):
                    if not _ABSOLUTE.match(m.group(1)):
                        out.append({"file": _rel(p, root), "line": i, "kind": "relative link", "match": m.group(1)[:100]})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evidence_kit.publication", description="Fail when a publication artifact contains a local path.")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="paths are reported relative to this directory")
    ap.add_argument("--forbid", action="append", default=[], help="an absolute path that must not appear (repeatable)")
    ap.add_argument("--allow", action="append", default=[], help="a regex for an intended match (repeatable)")
    ap.add_argument("--relative", action="store_true", help="also report relative links in Markdown and HTML")
    a = ap.parse_args(argv)
    missing = [p for p in a.paths if not p.exists()]
    for p in missing:
        print(f"missing: {p} (a named path that cannot be opened is never a clean result)")
    if missing:
        return 2
    files = expand(a.paths)
    found = local_path_findings(files, a.root, forbid=[*a.forbid, Path.home()], allow=a.allow)
    if a.relative:
        found += relative_link_findings(files, a.root)
    for f in found:
        print(f"{f['file']}:{f['line']}: {f['kind']}: {f['match']}")
    print(f"findings: {len(found)} in {len(files)} file(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
