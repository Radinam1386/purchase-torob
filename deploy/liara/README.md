# One-service Liara deployment

The Docker image runs the existing Next.js UI on port 3000 and the Python API on localhost:8000. Next rewrites `/api/*` to that internal API. Only port 3000 is published. The Python entry point forwards shutdown to both processes and exits if either process fails.

The `catalog` disk is mounted at `/app/data`. First boot expands a clean dataset snapshot only when `torob.sqlite` does not exist. Later releases preserve the live database, Mock histories and buyer reports. Both services run as UID 10001 after volume initialization.

`prepare.py` creates `output/liara/app.tgz` from explicit source paths and a SQLite backup. It removes local inquiry and buyer report rows from the copy, checks the database, and excludes `.env`, local logs, caches, dependencies and test output. The original local database is unchanged. The archive is approximately 102 MB for the current dataset.

Run from the repository root with the existing Python environment containing httpx and python-dotenv:

```text
python deploy/liara/check.py
python deploy/liara/prepare.py
python deploy/liara/publish.py provision
python deploy/liara/publish.py configure
python deploy/liara/publish.py deploy
python deploy/liara/publish.py status
```

If the remote build exceeds its time limit, build the existing cached dependencies locally with `NEXT_STANDALONE=1 AGENT_API_INTERNAL=http://127.0.0.1:8000 node web/node_modules/next/dist/bin/next build web`, then run `python deploy/liara/prepare_cached.py` and `python deploy/liara/publish.py deploy cached.tgz`. This packages the generated server, static assets and public files; the Linux runtime image still installs Python dependencies normally. The cached build must receive the same live browser checks as a remote build.

`publish.py` targets app `purchase-torob` in the existing `hackathon` team. It reads `LIARA_API_TOKEN` from the ignored root `.env`, sends only the allowlisted application settings to Liara, and never uploads the Liara token to the application. It reuses the app and disk on subsequent runs. A failed source upload must finish or fail before retrying deployment; `release.json` records a successful release submission.

Selected resources: `medium-g2`, 1 GB RAM, one replica, `basic` features, 2 GB persistent disk within the plan's 10 GB allowance. The account API quoted 825,000 + 475,000 = 1,300,000 tomans per 720 hours at setup. This is an estimate at continuous operation, not a spending cap; taxes, model usage and any separately billed usage are additional. No automatic scaling or paid calling provider is configured.

Local container builds were unavailable because Docker is not installed on this machine. Liara performs the Linux image build. Deployment state and build output are kept locally in `output/liara`; the live app must pass HTTP and browser checks before being reported ready.
