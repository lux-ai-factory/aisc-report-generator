# Changelog of the AISC report renderer (report-generator)

## Unreleased: proof files, exported results, conversations

- New block Exported results (`superset_exports`): the plots saved from the results dashboard with Save to
  report, one subsection per dashboard, each with its filters as tags, the saved SVG (prepared for print, not
  redrawn), who saved it, when, and the comment. It shows every saved plot, whatever AI card version or period
  it shows, and says so. Reads `aisc_report_plot` in the superset database. Check:
  `tests/test_block_superset_exports.py`.
- Key figures gains, for a test with conversation results (LangBiTe on Mijke), the share of conversations in
  which a person was sent where the baseline was, per target, pooled over the runs in the selection and saying
  over how many. Check: `tests/test_key_figures_conversations_unit.py`.
- Test results no longer lists conversation results row by row (also when a tool renderer fails and the
  generic table is drawn); one notice says how many were left out. Check: `tests/test_results_by_test.py`.
- Summary and coverage has the option `merge_label` (off by default): one column with the objective and its
  label, the description twice as wide.
- Risk identification has the option `show_classification` (on by default): off hides the operators and the
  AI Act risk class above the risks.
- The chart list of a dashboard chart block offers the most recently changed chart first, not by name.
- StrongREJECT's headline in Key figures is Jailbreak resistance only: Harmfulness and Worst jailbreak are
  no longer shown there (they stay in Test results).

- The control answers block lists, under each answer, the files that prove it (name, type, size, who attached
  it, when, SHA-256), read from `controls.submission_answer_file`; the files are never embedded. An answer row
  that holds only files (no answer, no score) counts as not answered and is not an answer given for another
  version; its files are listed. A project database without the table (controls migrations before
  2026-11-01) lists none. Check: `tests/test_block_control_answers.py`.

## 2026-10-19: closed submissions as they were answered

- The control answers (and what reads them: key figures, coverage, the checklist chart) show a closed
  submission's questions as they were when it was closed, answers to questions removed since included; a
  draft follows today's questions, as the controls app does (`views.answer_sheet`, after
  `apps/controls/src/lib/answerSheet.ts`). The block's submission line says "Answered under template
  revision N" for a closed submission that recorded it. Reads `submission_answer.question_text`,
  `question_article`, `question_order` and `submission.questions_version`: needs the controls migrations of
  2026-10-18 on every project database first.

## 2026-10-16: review fixes

Security:
- An SVG logo holding an `<image>`, `<feImage>` or `<foreignObject>`, or any href, is a 422: the size cap
  read only the root's declared size, so a small SVG embedding a 12000 x 12000 PNG passed it and took
  over 1 GB to draw (`tests/test_style.py`). Such a logo, accepted before, is now refused.
  `defusedxml` (already installed with cairosvg) is a direct dependency.

## 2026-10-14: review pass (branch pass/report-2026-10-13)

Areas: `report_service.py`, `report_renderer/style.py`, `docx.py`, `data/`, `blocks/`, `declared.py`,
`coverage.py`, `views.py`, the tests and the bundled plugins' tests.

Security:
- `/v1/render` is bounded: a body over `REPORT_RENDER_MAX_BYTES` (default 8 MiB) is 413 `too_large`
  before it is parsed; past `REPORT_RENDER_CONCURRENCY` renders at once (default 4) the answer is 503
  `busy`. A value that is not a positive whole number stops the start.
- SVG logos are capped by their declared size: one without width and height (nor viewBox), or over 16
  million pixels at twice its size, is a 422. The Word export draws any SVG at most 2000 px per side.
  An SVG logo with no size, accepted before, is now refused.

Fixes:
- Dashboard comments deleted in Superset (and their replies) are left out of reports.
- A declared table keeps a score column unless every row is exactly 1.
- Coverage logs a tool renderer's failing `verdict()` with an error ref.
- The Chart block draws a negative mean below the zero line (no forced 0 axis).
- Changes since sees a metric change past the 200th row.
- A stated AI Act risk class prints its label, not its id.
- Metric choices come from one query of the distinct (tool, metric) pairs.
- Controls reads use the remembered project-database lookup; the marking labels live in one place.

Removed:
- Routes `GET /v1/languages` and `POST /v1/coverage-choices` (401 without a token, 404 with one);
  `/health` still lists the languages. Dead code with them (`RunsView.skipped` and its notice,
  `engine.evaluation_choices`, `platform.database_exists`, and others).
- setuptools output under `plugins/*/build/` is no longer tracked.
- Duplicate and grep-only tests (a test audit).

Check:
- `env -u DATABASE_URL -u PLATFORM_TEST_DATABASE_URL uv run --extra dev pytest -q -p no:cacheprovider tests`
  (844 passed at the end of the pass); each plugin:
  `cd plugins/<tool> && uv run --extra dev pytest -q`.
- On a running stack: a `/v1/render` body over 8 MiB answers 413; `GET /v1/languages` answers 404; a
  template with a 16000 px SVG logo answers 422 at render.
