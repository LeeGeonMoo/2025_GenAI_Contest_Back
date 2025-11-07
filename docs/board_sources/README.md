# Board Catalog & Adapter Workflow

1. **Catalog File**: `catalog.json` contains board entries with keys:
   - `id`, `college`, `department`, `url`, `template`, `requires_auth`, `notes`.
   - Templates currently supported: `wordpress_board`, `snu_scholarship_html`.
2. **Loader**: `app/ingest/catalog.load_catalog` turns JSON into `BoardEntry`.
3. **Adapters**: `app/ingest/adapters.create_source` maps entries to specific
   `HTMLNoticeSource` implementations. Unsupported templates are logged and skipped.
4. **Execution**: When `BOARD_CATALOG_PATH` is set (default points to this folder),
   `scripts/run_ingest.py` automatically includes catalog-driven sources on top
   of the manually registered dummy ones.
5. **Extending**:
   - Add a new entry to `catalog.json`.
   - Implement or reuse a template adapter (e.g., new HTML parser) and register it
     in `app/ingest/adapters.py`.
   - Run `make ingest` to fetch data. Watch the console for warnings about missing adapters.
