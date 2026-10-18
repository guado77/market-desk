#!/usr/bin/env python3
"""Blocca la pubblicazione se in assets/ c'e' qualcosa di non ammesso:
estensioni diverse da png/pdf/xlsx, nomi non validi su Windows, o testo che
somiglia a un segreto (token GitHub/Telegram/xAI, chiavi private, password)."""
import os, re, subprocess, sys, zipfile
BAD_NAME = re.compile(r'[:?*"<>|\\]')
SECRET = re.compile(rb"(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|xai-[A-Za-z0-9]{20,}|\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{32,}|(?i:api[_-]?key|password|passwd|secret)\s*[=:]\s*['\"]?[A-Za-z0-9/+_-]{12,})")
def texts(path, data):
    yield data
    if path.endswith(".pdf"):
        try:
            yield subprocess.run(["pdftotext", "-q", path, "-"], capture_output=True, timeout=60).stdout
        except Exception:
            pass
    if path.endswith(".xlsx"):
        try:
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if n.endswith(".xml"):
                        yield z.read(n)
        except zipfile.BadZipFile:
            pass
problems = []
for root in sys.argv[1:]:
    paths = [root] if os.path.isfile(root) else [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]
    for p in paths:
        name = os.path.basename(p)
        if BAD_NAME.search(name) or name.endswith((".", " ")) or len(name) > 150:
            problems.append("nome non valido: " + p)
        if os.path.isfile(root) is False and not name.lower().endswith((".png", ".pdf", ".xlsx", ".gitkeep")):
            problems.append("estensione non ammessa: " + p)
        with open(p, "rb") as fh:
            data = fh.read()
        for t in texts(p, data):
            m = SECRET.search(t)
            if m:
                problems.append(f"possibile segreto in {p}: {m.group(0)[:12]!r}...")
                break
for x in problems:
    print("::error::" + x)
print("controlli:", "OK" if not problems else f"{len(problems)} problemi")
sys.exit(1 if problems else 0)
