# Java Contract Fixtures

Fixtures are JSON files containing a version, endpoint, request metadata and a
base64-encoded raw HTTP response body. Credentials, cookies, passwords, files
and signed URLs are redacted before persistence.

Record fixtures with:

```bash
python tools/record_java_contracts.py \
  --base-url "$JAVA_BASE_URL" \
  --scenario-file tests/contracts/scenarios/foundation.yaml \
  --output tests/contracts/fixtures/foundation
```
