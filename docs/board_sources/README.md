# Board Catalog & Adapter Workflow

1. **Catalog File**: `catalog.json` contains board entries with keys:
   - `id`, `college`, `department`, `url`, `template`, `requires_auth`, `notes`.
   - Templates currently supported: `wordpress_board`, `snu_scholarship_html`.
2. **Loader**: `app/ingest/catalog.load_catalog` turns JSON into `BoardEntry`.
3. **Adapters**: `app/ingest/adapters.create_source` maps entries to specific
   `HTMLNoticeSource` implementations. Unsupported templates are logged and skipped.
4. **Execution**: When `BOARD_CATALOG_ENABLED=true` (and `BOARD_CATALOG_PATH` is set),
   `scripts/run_ingest.py` automatically includes catalog-driven sources on top
   of the manually registered dummy ones. 기본값은 `false`라서 더미 데이터만 수집합니다.
5. **Extending**:
   - Add a new entry to `catalog.json`.
   - Implement or reuse a template adapter (e.g., new HTML parser) and register it
     in `app/ingest/adapters.py`.
   - Run `make ingest` to fetch data. Watch the console for warnings about missing adapters.

## Local Dummy Dataset
- `docs/dummy_notices/notice_*.html` contains synthetic notices generated via
  `python scripts/create_dummy_dataset.py` (defaults to 120 entries with diverse layouts).
- `LocalDummyDatasetSource` loads this directory so you can test LLM 요약/임베딩/분류와
  Mongo/Qdrant 저장을 실제 크롤러 없이 검증할 수 있습니다.
