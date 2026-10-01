# TeachX architecture

## Product boundary

TeachX is intentionally web-first. The browser is the only supported client.
The first release keeps four product surfaces:

1. Chat with streaming agent output.
2. Capabilities such as solve and quiz.
3. Knowledge-grounded retrieval.
4. Settings for models and learning preferences.

## Runtime path

```text
Next.js UI
  -> /ws unified turn protocol
  -> TurnService
  -> AgentRuntime
  -> Provider adapter
  -> Tool registry
  -> Session repository
```

## Backend modules

- `api`: HTTP and WebSocket adapters.
- `runtime`: agent loop, capabilities, and tools.
- `providers`: mock and OpenAI-compatible model adapters.
- `storage`: durable sessions and turn events.

## Design rules

- The WebSocket protocol is the product seam used by the frontend.
- Providers are adapters behind one small interface.
- Tools describe themselves once and are executed through one registry.
- Persistence owns message history and event replay.
- Production dependencies may replace adapters without changing the runtime.
