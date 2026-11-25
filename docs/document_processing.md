# Document processing with DOST-Catalyst

DataSpace can send a PDF resource to [DOST-Catalyst](https://github.com/CivicDataLab/DOST-Catalyst),
a separate document-processing service built on Docling. Catalyst returns the tables as
Markdown, the sentences as CSV, the sentences that were not extracted properly as CSV, and the
images as a ZIP. DataSpace stores these files privately next to the resource.

**Processing never starts by itself.** An upload does nothing. A resource is processed only when
all of these are true:

- `DOCUMENT_PROCESSING_ENABLED=True` (off by default);
- a superuser (Keycloak realm role `admin`) asks for it;
- the resource has a PDF file;
- the resource is not already waiting for or in a job.

## How it works

```text
Admin asks ─► ResourceProcessing row, status REQUESTED
                 │
   worker (manage.py run_document_processing)
                 ├─ POST the PDF to Catalyst /api/jobs        → RUNNING
                 ├─ GET /api/jobs/{id} each round until done
                 ├─ download the outputs → ProcessedFile rows (private S3)
                 └─ DELETE the Catalyst job                   → DONE or FAILED
```

| Part | Where |
|---|---|
| Models `ResourceProcessing`, `ProcessedFile` | `api/models/ResourceProcessing.py` |
| Request rules (switch, superuser, PDF, one job) | `api/services/document_processing.py` |
| Catalyst HTTP client | `api/services/catalyst_client.py` |
| Worker | `api/services/document_worker.py`, `api/management/commands/run_document_processing.py` |
| Django admin | `api/admin.py`: filters and actions on Resources, a Resource processings page |

Output files are stored under `<STORAGE_ENV>/private/resources/processed/<resource_id>/`.
Deleting a resource or its processing record also deletes the S3 objects. When the resource file
changes after processing, the Resources list shows the result as "file changed"; it is not
processed again until an administrator asks.

There is no GraphQL API and no frontend for this feature: administrators use the Django admin.

## Use it in the Django admin

1. Open **Resources**. Filter by format "PDF" and by processing status (for example "Never
   processed" or "Done, but the file changed").
2. Tick the resources, choose **Process selected documents with DOST-Catalyst** and click **Go**.
   The action shows only to superusers, and only when the switch is on. A message says how many
   documents were requested and why the others were skipped.
3. Open **Resource processings** to follow the status. A finished row lists its output files,
   which you can download from there.
4. **Cancel selected requests** cancels a waiting request at once; for a running job it asks the
   worker to stop it.
5. **Delete** a processing row to remove its output files. A waiting or running row must be
   cancelled first.

The admin action uses RapidOCR, which is free and runs inside Catalyst. The request record also
holds options for full-page OCR and for Sarvam OCR (which costs money and sends page images to
Sarvam); the admin action does not set them yet.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `DOCUMENT_PROCESSING_ENABLED` | `False` | The global switch. Off: no new request and no new job |
| `CATALYST_URL` | `http://catalyst:8000` | Catalyst, reachable from the worker only |
| `CATALYST_USERNAME`, `CATALYST_PASSWORD` | `dost`, empty | Catalyst's HTTP Basic credentials |
| `CATALYST_POLL_SECONDS` | `10` | Pause between worker rounds when nothing changed |
| `CATALYST_MAX_WAIT_MINUTES` | `45` | A job that runs longer fails. Keep it under Catalyst's `CATALYST_JOB_TTL_MINUTES` (60) |

## Run it locally

1. Build the Catalyst image in the DOST-Catalyst repository: `docker build -t dost-catalyst .`
2. In `.env`, set `DOCUMENT_PROCESSING_ENABLED=True` and a `CATALYST_PASSWORD`.
3. Start the two extra services, which are in the Compose profile `processing`:

   ```bash
   docker compose --profile processing up -d catalyst document_worker
   ```

   A plain `docker compose up` does not start them.
4. Ask for processing in the Django admin.

The first conversion downloads the Docling models (about 500 MB) into the `catalyst-models`
volume.

## Deploy

- Run Catalyst with 4 GB of memory or more (`CATALYST_MEMORY`, default `6g` in Compose). Do not
  publish its port: only the worker needs it.
- Run one worker per environment (more are safe, but one is enough). It needs little memory,
  because Catalyst does the heavy work.
- The worker needs the same database, S3 settings and `CATALYST_*` variables as the backend.
- Leave `DOCUMENT_PROCESSING_ENABLED=False` until Catalyst and the worker run.

## Failures

| Case | What the worker does |
|---|---|
| Catalyst is down or its waiting line is full | The request stays REQUESTED and starts later |
| Catalyst lost the job (restart) | FAILED: "Catalyst lost the job … Process it again." |
| The job runs longer than `CATALYST_MAX_WAIT_MINUTES` | The job is deleted, FAILED |
| The worker restarts | Running jobs continue from their job ID |
| An admin cancels a running job | The worker deletes the Catalyst job, then CANCELLED |
