---
description: |
  [TOPIC] Scientific PDF Reports — delivery & tracking
  [DETAILS] How a finished report reaches collaborators and stays traceable: the mandatory email contents (PDF attachment, issue-tracker URL, summary, timestamped subject, source-machine file path), the subject-line format, a worked `smtplib` MIMEMultipart send with a pre-attach size check, and the post-delivery issue-comment that turns the tracking issue into the canonical delivery log. Split from [`03_reporting_01_pdf-reports.md`](03_reporting_01_pdf-reports.md).
tags: [scitex-scientific-reporting-pdf-reports]
---

# Scientific PDF Reports — delivery & tracking

Delivery and tracking half of [`03_reporting_01_pdf-reports.md`](03_reporting_01_pdf-reports.md)
(which covers naming, structure, bookmarks, figures, and size management).

## Delivery: Email Rules

Every delivery email MUST include:

1. **PDF attachment** (the report itself — never just inline PNGs).
2. **Issue-tracker URL** in the body, linking to the tracking issue
   (e.g. `https://github.com/<org>/<repo>/issues/<n>`).
3. **Summary** of key findings in the email body (mirrors the executive
   summary section).
4. **Timestamp** in the subject line.
5. **File path** on the source machine, for collaborators with shared
   filesystem access.

Subject format:

```
[<Project>] <Analysis> Report YYYY-MM-DD — <one-line key finding>
```

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

msg = MIMEMultipart()
msg["Subject"] = f"[{project}] {analysis} Report {date} — {summary}"
msg["From"] = from_addr
msg["To"]   = to_addr

body = f"""\
{project} {analysis} Report

Tracking issue: {issue_url}

Key findings:
- {finding_1}
- {finding_2}

Report on <host>: {report_path}
"""
msg.attach(MIMEText(body, "plain"))

with open(report_path, "rb") as fh:
    part = MIMEBase("application", "pdf")
    part.set_payload(fh.read())
encoders.encode_base64(part)
part.add_header("Content-Disposition", f'attachment; filename="{report_path.name}"')
msg.attach(part)

with smtplib.SMTP("localhost", 25) as server:
    server.sendmail(from_addr, [to_addr], msg.as_string())
```

Check `report_path.stat().st_size < 10 * 1024 * 1024` before attaching;
fall through to size-management above on failure.

## Tracking: Issue Comment

After successful delivery, comment on the tracking issue so the
delivery history lives next to the analysis spec:

```bash
gh issue comment <n> --repo <org>/<repo> --body "$(cat <<EOF
Report delivered: $(basename "$report_path")
Path: $report_path
Size: $(du -h "$report_path" | cut -f1)
Email: sent (or: failed — <reason>)
EOF
)"
```

The issue thread becomes the canonical delivery log: every report PDF is
discoverable from the analysis ticket, and failures are visible to
everyone watching the issue.
