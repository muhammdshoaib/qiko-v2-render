# Policy releases: frozen legal text

Each file here is a snapshot of a legal page (terms, privacy, cookies) at one
release point in time, named `<release-id>.tsx` and pinned by the sha256 digest in
`CURRENT_POLICY_RELEASES` in `../models.py`.

These files are compliance evidence: `ConsentService` writes the digest into
append-only `ConsentRecord` rows, so each record states which exact legal text the
user agreed to. The archive is what lets us produce that text years later, after
the live page has changed or been removed.

Rules:

- Never edit, reformat, or "fix" an existing file. A single changed byte breaks
  every consent record that cites its digest.
- A new version of a policy means a NEW file with a NEW release id added
  alongside, plus a new entry in `CURRENT_POLICY_RELEASES`. Never change an
  existing release in place.
- Keep them out of formatters and linters: they are verbatim copies, not code
  that must satisfy a style rule.
