# Jazz automation

The worker uses `JAZZ_UAN` and `JAZZ_PASSWORD` from `.env`. No browser setup is
required. Separate persistent Playwright profiles let ingestion and recording
downloads run concurrently. A missing or expired session triggers automatic login
through `/Businessvpbx/admin/user/loginvpbx` (`diodid`, `password`, `Log in`).
An interactive security challenge is reported as `JAZZ_AUTH_BLOCKED`.

## Verified portal hierarchy (2026-09-25)

`VPBX Reports → Outbound CDRs` and `VPBX Reports → Inbound CDRs` lead to
`/Businessvpbx/admin/vpbxadmin/cdr_details_outbound` and
`/Businessvpbx/admin/vpbxadmin/cdr_details_inbound`. Both screens have
`#startDate`, `#endDate`, Search, and `#table_cdr`. The portal sends an AJAX GET
with `start_date` and `end_date` and returns **all** matching rows. DataTables
paginates the returned table locally, so the adapter parses the complete server
response instead of relying on the visible ten-row page.

The verified columns are `Call Date Time`, `Ext No`, `Client Number`, `Duration`,
`Bill Sec`, `Call Status`, `Call Type`, and `Call Recording`. The inbound screen
swaps the positions of `Ext No` and `Client Number`; parsing uses headers. The
`Client Number` field is the remote customer for either direction. `Call Type`
contains `inbound` or `outbound`. Observed statuses were `ANSWERED`, `NO ANSWER`,
and `BUSY`; raw text is retained alongside the canonical status.

Each CDR recording link opens `/admin/vpbxadmin/callrecording/{id}`. The detail
page exposes an `<audio><source src="...wav">` and a `Download Call Recording`
link to the same WAV. The authenticated Playwright request context fetches that
WAV; `ffprobe` and SHA-256 verify the file before private Appwrite upload. The
recording detail ID is retained as `source_call_id`, but it is shared by several
inbound routing legs, so deduplication also includes stable row metadata.
An answered recording with no detected speech becomes `NO_SPEECH`; it remains
in the telephony counts and is never given a fabricated transcript or grade.

`VPBX Manager → Extensions Details` identifies the exact Saima and Kiran
extension rows. Jazz displays their mobile numbers without a leading zero in
the CDR `Ext No` field. The sync refreshes those mappings in the agents table.
Shared labels such as `Rimsha/Saima` are left unresolved.

## Continuation

Office hours are 09:30–18:00 Karachi. Today's automatic batch is released at
18:01; morning startup waits for that release and only catches up missed closed
batches. A first run at or after 18:01 queries the current Karachi date through
18:00. Later batches use the newest persisted Jazz timestamp and overlap, and
also query the preceding date for calls after 18:00 assigned to the current batch.
Calls after 18:00 today are left for tomorrow's 18:01 batch, including their AI jobs.
The unique dedupe index prevents repeated rows. Processing jobs have separate
checkpoints and leases, so an AI failure does not hold back Jazz discovery.

The main sync runs at 18:01 Asia/Karachi. Startup and hourly catch-up retry only
closed batches that have not synced successfully. Audio retention is measured from the actual call timestamp,
with transcription allowed to finish before an overdue file is deleted.

## Optional diagnostic

`cd services/backend && uv run python ../../scripts/jazz_inspect.py --date YYYY-MM-DD`
logs in and scans automatically, printing counts and headers without phone
numbers. `--headed` only shows the browser; `--snapshot PATH` writes a sanitized
table fragment. This utility is not part of normal setup or operation.
