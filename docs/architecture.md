# Architecture and evidence model

```mermaid
sequenceDiagram
  actor Operator
  participant UI as Browser console
  participant API as FastAPI/WebSocket
  participant Store as SQLite + artifacts
  participant Runtime as Incident runtime
  participant Provider as Text/Vision/STT adapter
  Operator->>UI: logs + image + WAV + message
  UI->>API: bounded multipart upload
  API->>Store: hash and persist artifact metadata
  Runtime->>Store: build deterministic timeline
  Runtime->>Provider: evidence + operator question
  Provider-->>Runtime: brief + usage
  Runtime->>UI: streamed stage events
  Runtime-->>Operator: approval request for remediation
```

## Trust boundaries

- Uploaded names are normalized and files are size-bounded.
- SHA-256 ties every derived result to an artifact.
- Timeline parsing is deterministic and separate from model interpretation.
- Provider calls are isolated behind one adapter and can remain fully offline.
- Remediation is advisory; even an approved proposal records `action_executed=false`.
- Interruption is a first-class state and emits an auditable event.

