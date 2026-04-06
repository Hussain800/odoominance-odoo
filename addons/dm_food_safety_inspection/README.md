# Dubai Food Safety Inspection

A workflow-first Odoo addon for restaurant and venue inspections.

## What it does

- Opens on a live dashboard with KPI cards, risk distribution, and recent inspections.
- Tracks inspections through draft, ready, in-progress, supervisor review, pass, fail, and cancel stages.
- Scores checklist lines with weighted risk and compliance calculations.
- Provides an advisory AI summary that can be reviewed before it is copied into the follow-up note.

## AI summary flow

- Generate a summary from the current inspection findings.
- Review the structured advisory output.
- Apply it to the follow-up note only when you want it persisted.

## Notes

- The dashboard uses the normal backend client action pattern.
- The AI summary falls back to a deterministic local summary when no OpenAI API key is configured.
- Workflow transitions are still guarded by server-side actions.
