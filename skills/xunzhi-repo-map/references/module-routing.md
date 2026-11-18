# Module Routing

| Request or symptom | Owning Skill | Python status |
| --- | --- | --- |
| App startup, settings, response envelope, shared resources | `xunzhi-repo-map` | Implemented Foundation |
| Identity, login, ownership, user isolation | `xunzhi-auth-user` | Planned |
| Interview sessions, questions, answers, scoring, follow-up, restore | `xunzhi-interview-domain` | Planned |
| General Agent sessions, messages, files, SSE | `xunzhi-agent-domain` | Planned |
| ASR, WebSocket media, notification, TTS | `xunzhi-media-domain` | Planned |
| Guard, rate limit, single-flight, task execution | `xunzhi-ai-runtime` | Foundation resources only |
| Cross-domain contract or migration change | `xunzhi-change-playbook` | Active |
| Failure investigation or recovery | `xunzhi-debug-playbook` | Active |

Foundation entry points:

- repo-path: `app/main.py`
- repo-path: `app/core/lifespan.py`
- repo-path: `app/core/settings.py`
- repo-path: `app/core/result.py`
- repo-path: `app/core/exception_handlers.py`
- repo-path: `app/infrastructure/mysql.py`
- repo-path: `app/infrastructure/mongodb.py`
- repo-path: `app/infrastructure/redis.py`
- repo-path: `app/infrastructure/http.py`
