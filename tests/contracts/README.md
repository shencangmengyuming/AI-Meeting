# Baseline Contract Fixtures

Fixtures are optional snapshots of the reviewed baseline API. They inform
Python behavior but are not runtime dependencies. Credentials, cookies,
passwords, files and signed URLs are redacted before persistence.

Record fixtures with:

```bash
python tools/record_java_contracts.py \
  --base-url "$JAVA_BASE_URL" \
  --scenario-file tests/contracts/scenarios/foundation.yaml \
  --output tests/contracts/fixtures/foundation
```
