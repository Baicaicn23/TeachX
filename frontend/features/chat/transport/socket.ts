export interface SocketMessageEvent {
  data: unknown;
}

export interface TurnSocket {
  readonly readyState: number;
  send(data: string): void;
  close(code?: number, reason?: string): void;
  addEventListener(
    type: "open" | "message" | "close" | "error",
    listener: (event: SocketMessageEvent) => void,
  ): void;
}

export type TurnSocketFactory = (url: string) => TurnSocket;

export const SOCKET_CONNECTING = 0;
export const SOCKET_OPEN = 1;

export function browserSocketFactory(url: string): TurnSocket {
  // scopedUrl() intentionally preserves same-origin paths such as
  // `/ws?dt_workspace=`. Resolve that path here so the browser always receives
  // an absolute ws:// or wss:// URL, including when the app runs behind a
  // local proxy or a reverse proxy.
  const absolute = new URL(url, window.location.href);
  absolute.protocol = absolute.protocol === "https:" ? "wss:" : "ws:";
  return new WebSocket(absolute) as unknown as TurnSocket;
}
