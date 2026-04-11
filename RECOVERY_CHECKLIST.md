# Steward recovery checklist

Use with `DEEP_REVIEW.md` and `PROGRESS.md` §0.

---

## Already in code

- [x] Storage **protocols** — `steward_service/storage/protocols.py`
- [x] **In-memory** stores (default) — `*_store.py` modules
- [x] **SQLite** durable path — `storage/sqlite_backend.py`, `storage/factory.py`, `STEWARD_STORAGE_*` env (`README.md`)
- [x] **JSON serialize/deserialize** for persisted rows — `storage/serialize.py`
- [x] **Institution expenditure** — authoritative **`data/institution_expenditure_rules.json`**, `institution_rules.py`, `institution_engine.py`
- [x] **`GET /policies/institution.expenditure.v1`** — metadata/version from JSON
- [x] **Audit public payload** — `InMemoryAuditStore.to_public_payload` for all backends
- [x] Approval / simulate / bulk / evaluate-proposal linkage (earlier remediation)
- [x] Tests **62** including **`test_sqlite_storage_durability`**, **`test_institution_engine`**

---

## Verify manually

- [ ] SQLite in production: backup `STEWARD_SQLITE_PATH`, single-writer constraints
- [ ] NemoClaw unchanged — same HTTP routes (`README` / sibling repo E2E)
- [ ] Edit `institution_expenditure_rules.json` → restart → behavior matches

---

## Likely missing / redo

- [ ] **Postgres** (or other) for HA / multi-worker
- [ ] **`build_execution_plan`** reads capability/tool/policy from published registry files
- [ ] **GP dedup** for repeated `/action/*` same content hash
- [ ] HTTP auth
- [ ] Rename institutional `decision_record_id` response field (breaking)

---

## Nice to have later

- [ ] `GET /proposals` list
- [ ] Approval revocation API
- [ ] Cross-store transactions
- [ ] External fact connectors for institution
