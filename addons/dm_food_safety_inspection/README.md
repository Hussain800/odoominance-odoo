# Dubai Food Safety Inspection

Workflow-first Odoo addon for food safety inspections, corrective findings, and certificate tracking.

## Features

- Dashboard-first operations with KPI cards, risk distribution, quick actions, and recent inspections.
- Inspection workflow with controlled transitions:
	- Draft -> Ready -> In Progress -> Waiting Supervisor -> Passed/Failed/Cancelled
- Weighted checklist scoring (compliance score, risk score, risk band, grade).
- AI advisory summary generation with manual apply-to-note workflow.
- Establishment food profile fields on contacts.
- Findings management with severity, status, overdue tracking, and violation tags.
- Certificates management with status transitions and expiry validation.
- Integration tabs/stat buttons inside the inspection form for findings and certificates.

## Menus Added

- Food Safety -> Establishments
- Food Safety -> Food Safety Inspections
- Food Safety -> Findings
- Food Safety -> Certificates
- Food Safety -> Configuration -> Templates/Stages/Grades/Violation Tags

## AI Summary Provider

The addon requests Groq when configured, and falls back to deterministic local summaries when it is not.

Environment variables:

- `GROQ_API_KEY` (required for AI mode)
- `GROQ_MODEL` (optional override, default: `llama-3.3-70b-versatile`)
- `GROQ_USER_AGENT` (optional override)

## Data Files Included

- Sequences for inspections/findings/certificates
- Inspection stages and grading bands
- Checklist template seed data
- Expanded demo data (`noupdate="1"`) across establishments, inspections, findings, certificates, tags, templates, and grades

## Security

- Role groups:
	- Inspector
	- Supervisor
	- Manager
- Company-aware access rules for inspections, findings, certificates, and violation tags.
- ACL coverage for newly added models.

## Quick Usage Flow

1. Open Food Safety Dashboard.
2. Start from a seeded establishment or create one.
3. Create/execute an inspection from a checklist template.
4. Submit for supervisor review.
5. Track findings and certificates from the integrated inspection tabs.
6. Generate AI summary and apply to follow-up note when approved.

## Update Command

```powershell
& '.\.venv\Scripts\python.exe' 'odoo-bin' -d 'dm_food_safety_validation' -u 'dm_food_safety_inspection' --stop-after-init
```

## Test Command

```powershell
& '.\.venv\Scripts\python.exe' 'odoo-bin' -d 'dm_food_safety_validation' -u 'dm_food_safety_inspection' --test-enable --stop-after-init
```
