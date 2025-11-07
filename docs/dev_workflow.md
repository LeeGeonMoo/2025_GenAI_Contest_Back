# Dev Workflow (Pre-Crawler)

## Common Commands
| Task | Command |
| --- | --- |
| Start stack | `make dev-up` |
| Stop stack | `make dev-down` |
| Run ingest pipeline | `make ingest` |
| Seed posts / users | `make seed-posts`, `make seed-users` |
| Run tests | `make test` |
| Tail API logs | `make logs` |

## Seeding Flow
1. `make seed-posts` – inserts sample notices.
2. `make seed-users` – creates a sample user with like interactions.
3. `make ingest` – runs multi-source ingest + LLM summarisation/embeddings.

## Manual Verification
- `GET /feed` → check `meta.scoring_weights` and `items[*].rank_reason`.
- `GET /feed/reco-likes?limit=5&user_id=<id>` → ensures semantic likes path.
- `GET /search?q=장학&mode=semantic` → verifies Qdrant queries.
- `POST /likes` / `DELETE /likes/{user}/{post}` → interaction endpoints.
- `POST /reminders` / `GET /reminders?user_id=` → reminder workflow.

## Notes
- LLM/Qdrant credentials go in `.env`. When missing, services use fallback logic.
- Scheduler is toggled via `SCHEDULER_ENABLED`. When enabled, dummy ingest runs periodically.
- `CRAWLER_SAMPLE_HTML` defaults to `docs/sample_pages/scholarship_board.html`. Replace it with a real URL (or `file://` path) to crawl live pages using the new HTML source.
- `BOARD_CATALOG_PATH` points to `docs/board_sources/catalog.json`. Each entry maps to an adapter (currently WordPress list + custom ones). Unsupported templates are logged and skipped.
