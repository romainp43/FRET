#!/usr/bin/env python3
"""Génère web/legal/*.html à partir de config/company.json et de la date de version.

  python3 tools/build_legal.py            # brouillon (les champs « À COMPLÉTER » restent visibles)
  python3 tools/build_legal.py --final    # échoue s'il reste un champ à compléter (à lancer avant la mise en ligne)

IMPORTANT : ces documents sont des BROUILLONS rédigés d'après les textes en vigueur (LCEN, RGPD, Code de commerce,
contrats types de transport). Ils doivent être relus et validés par un avocat avant publication.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from legal_texts import PAGES, VERSION  # noqa: E402

PLACEHOLDER = re.compile(r"\[À COMPLÉTER[^\]]*\]")
TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — FRETRAU</title><link rel="icon" type="image/svg+xml" href="/favicon.svg"><link rel="stylesheet" href="/styles.css"></head>
<body class="legal"><header class="top"><div class="wrap"><a class="brand" href="/"><img src="/logo-mark.svg" alt="" width="28" height="28">FRET<b>RAU</b></a>
<nav>{nav}</nav></div></header>
<main class="wrap legal-body"><h1>{title}</h1><p class="muted">Version du {version}</p>{body}</main>
<footer><div class="wrap">{nav}</div></footer></body></html>
"""


def render(company):
    def fill(text):
        out = text
        for k, v in company.items():
            out = out.replace(f"[[{k}]]", html.escape(str(v)))
        return out
    nav = " ".join(f'<a href="/legal/{slug}.html">{html.escape(p["title"])}</a>' for slug, p in PAGES.items())
    pages = {}
    for slug, p in PAGES.items():
        pages[slug] = TEMPLATE.format(title=html.escape(p["title"]), body=fill(p["body"]), version=VERSION, nav=nav)
    return pages


def main():
    final = "--final" in sys.argv
    with open(os.path.join(ROOT, "config", "company.json"), encoding="utf-8") as f:
        company = json.load(f)
    pages = render(company)
    left = sorted({m for h in pages.values() for m in PLACEHOLDER.findall(h)})
    if final and left:
        print("ÉCHEC : champs à compléter dans config/company.json :")
        for m in left:
            print("  -", m)
        sys.exit(1)
    os.makedirs(os.path.join(ROOT, "web", "legal"), exist_ok=True)
    for slug, h in pages.items():
        with open(os.path.join(ROOT, "web", "legal", slug + ".html"), "w", encoding="utf-8") as f:
            f.write(h)
    print(f"{len(pages)} pages générées (version {VERSION}) ; champs restant à compléter : {len(left)}")


if __name__ == "__main__":
    main()
