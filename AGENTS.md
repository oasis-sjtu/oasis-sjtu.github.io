# Oasis Lab Site Agent Context

This repository is the Oasis Lab static website. Treat publication changes as a structured workflow, not as a plain CSV edit.

## Publication Change Workflow

When adding or editing publications:

1. Update `static/publications.csv` using the existing column order.
2. Add `url_page` whenever an official paper, DOI, conference, ACM, IEEE, USENIX, or author page is available. It is not mandatory before a page exists.
3. Once a downloadable camera-ready or public PDF exists, download it by default and host it in `static/papers/`, referenced as `../static/papers/<file>.pdf`.
4. For ACM/IEEE publisher PDFs, use the user's logged-in Chrome session when needed. If access fails, ask the user to sign in to ACM DL / IEEE Xplore / SJTU access and retry.
5. Do not infer `url_code` or `url_dataset` from general web search. Only fill them from links extracted from the paper PDF itself.
6. If adding a PDF, scan it for repository and dataset candidates:

   ```sh
   ./venv/bin/python scripts/manage_publication_pdfs.py --extract-links
   ```

7. For the publication being added or edited, check `url_video` and `url_slides`. Fill them when official pages expose them; absence is acceptable only after checking.
8. Use each publication update as a backfill pass for recent work: review the 10 most recent publications in `static/publications.csv` for newly available `url_page`, downloadable/localizable `url_pdf`, `url_video`, `url_slides`, and official talk/video pages. Do not do a full web backfill for older publications unless the user asks or the audit/link checks point to a specific issue.
9. If the recent-10 backfill adds any PDF, localize it in `static/papers/` and scan it for repository and dataset candidates before filling `url_code` or `url_dataset`.
10. Check all publication links:

   ```sh
   ./venv/bin/python scripts/manage_publication_pdfs.py --check-links
   ```

11. Build the site:

   ```sh
   ./venv/bin/python freeze.py
   ```

If a remote site returns 403 or times out due to anti-bot behavior but opens in a normal browser, treat it as reachable after browser verification and document the judgment in the handoff summary.
