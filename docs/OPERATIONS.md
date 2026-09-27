# Operations

Office hours are 09:30–18:00 Asia/Karachi. The discovery Function releases each day's
Jazz discovery and processing batch at 18:01. Calls after 18:00 are included in
the following day's 18:01 batch. Morning startup does not process today's calls.
Startup and hourly checks retry only missed closed batches, using the source
cursor with overlap; successful batches are not rediscovered throughout the day.
The worker recovers stale leases and incomplete call checkpoints on each scheduled execution.
Routine operation requires only opening the dashboard.

The System page exposes Jazz authentication, page, download, and job failures.
An unexpected CAPTCHA or OTP is reported as `JAZZ_AUTH_BLOCKED`; ordinary session
expiry triggers automatic re-login. Failed AI jobs retain their already uploaded
recordings and retry with backoff. After each bounded burst of attempts, transient
failures pause for `JOB_RETRY_COOLDOWN_SECONDS` (default 30 minutes), then resume
automatically. Admin retry controls remain optional diagnostics for permanent
validation failures after their underlying cause is fixed.

`docs/DEPLOYMENT.md` covers deployment, backups, reporting, and retention.
