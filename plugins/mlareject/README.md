# aisc-report-plugin-mlareject

The MLA-Reject tool renderer: it draws the runs of the MLA-Reject test inside the Test results block of an AISC
report (step 4 Collect evidence, Report). It is one of the four tool renderers bundled with the report renderer
(`report-renderer`, `apps/report-generator`), next to LangBiTe, Promptfoo and StrongREJECT, and is installed with
it. See the renderer's [README](../../README.md) for how reports are drawn.

## What it shows

The section is computed from the run's measurements alone (no database read). One case is one measurement whose
metric is `score`; its language, jailbreak method and harm category come from the measurement's dimensions
(`language`, `jailbreak`, `category`; "unknown" when missing).

- **Executive summary**: total observations, mean score, empty and effective jailbreaks, the share of empty
  ones, and the languages, jailbreak methods and categories seen.
- **Aggregate score by jailbreak method**, **Most susceptible harm categories** and **Scores by language**: per
  group, the cases, the harmful cases, the empty cases and the mean score, highest mean first.

A case scoring below 1.5 (`THD` in `statistics.py`) counts as an empty jailbreak; 1.5 or above counts as harmful
(effective). MLA-Reject defines no pass or fail, so the section shows none and `verdict()` is `None`. The section
never shows a prompt or a response.

## How it is found

The package declares the entry point `aisc_report.tools`: `mlareject =
"aisc_report_plugin_mlareject:MLAREJECTToolRenderer"`. `MLAREJECTToolRenderer` subclasses `BaseToolRenderer`
from `aisc-report-plugin-interface` (`shared/report-plugin-interface` in the aisc repository) and claims the tool
`MLA-Reject`.

## Files

| path | contents |
|---|---|
| `aisc_report_plugin_mlareject/tool_renderer.py` | `MLAREJECTToolRenderer` |
| `aisc_report_plugin_mlareject/statistics.py` | `compute_statistics(measurements)`: the summary and the groups |
| `aisc_report_plugin_mlareject/templates/tool_section.html.j2` | the section's HTML |
| `tests/` | the tests |

## Tests

From `apps/report-generator/plugins/mlareject`, in a full aisc checkout (the plugin interface is taken from
`../../../../shared/report-plugin-interface`):

```bash
uv run --extra dev pytest -q
```
