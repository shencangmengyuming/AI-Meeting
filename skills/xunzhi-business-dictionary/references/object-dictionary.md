# Object Dictionary

| Term | Meaning | Constraint |
| --- | --- | --- |
| `user_id` | Durable ownership identity | Authorization and isolation use this, not display names. |
| `session_id` | Domain session identity | Its namespace belongs to the domain; do not assume Agent and interview sessions are interchangeable. |
| `request_id` | Stable request or idempotency identity | A client retry must retain it when the operation is the same. |
| `question_number` | Business-facing interview question identity | It may describe a main question or follow-up; it is not automatically a database key. |
| runtime state | Mutable execution progress | It can be rebuilt and is not the durable business truth by itself. |
| snapshot | Recoverable projection of current state | Version and source must be explicit. |
| turn | One user/system interaction record | It supports replay, audit, and recovery; it is not the score record itself. |
| committed result | Business outcome accepted by the main flow | Side records may be compensated without rerunning the outcome. |

Python naming uses snake_case internally. External JSON aliases remain an API
compatibility decision and must be covered by contract tests.
