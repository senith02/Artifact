# Dissertation figures

Every figure in Chapters 4 and 5, ready for Word. For each figure there is:
- a `.png` at 300 dpi or 3× scale (Insert → Pictures);
- an `.svg` (editable vector; Word 365 can insert it directly).

`../word/figures_gallery.docx` has every figure with its caption, sized to an A4 text block, for
copy-and-paste.

| Kind | Figures | Made by | Data source |
| :-- | :-- | :-- | :-- |
| Diagrams | 4.1–4.10, 4.12, 4.13, 4.16, 4.18 | `src/*.mmd` rendered by `src/render_diagrams.ps1` (Mermaid CLI) | Checked against `code/scheduler_core/`, `code/advisor/`, `code/github-action/` and the decision log |
| Charts | 4.11, 4.14, 4.15, 4.17, 4.19, 4.20, 5.1, 5.2 | `code/scripts/make_dissertation_figures.py` | Read only from `results/` and `code/data/carbon/` (file named per figure in the script) |
| Screenshot | 4.23 | Headless Edge render of `results/p4/whatif/senith02__carbon-advisor-demo/report.html` | The saved What-If report |

Figures 4.21 and 4.22 are screenshots to take from the demo repository's Actions page; the run links
are given under each caption in Chapter 4.

**Regenerate**
- Charts: from `code/`, `python scripts/make_dissertation_figures.py`.
- Diagrams: `src\render_diagrams.ps1 -Mmdc <path to mmdc> [-Puppeteer <config pointing at a browser>]`.
- Word files: from `dissertation/`, `python build_word.py` (needs `pypandoc_binary`, `python-docx`
  and `pillow`; not part of the research stack).
