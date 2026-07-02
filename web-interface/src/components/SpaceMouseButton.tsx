import { useSpaceMouse } from "../hooks/useSpaceMouse";

interface Props {
  onMotion?: (motion: import("../lib/spacemouse").SpaceMouseMotion) => void;
}

export default function SpaceMouseButton({ onMotion }: Props) {
  const { supported, connected, deviceName, error, connect, disconnect } = useSpaceMouse(onMotion);

  if (!supported) return null;

  return (
    <div className="spacemouse-control">
      {connected ? (
        <button
          type="button"
          className="spacemouse-btn connected"
          title={deviceName ?? "SpaceMouse connected"}
          onClick={() => disconnect()}
        >
          <span className="spacemouse-dot" aria-hidden />
          SpaceMouse
        </button>
      ) : (
        <button
          type="button"
          className="spacemouse-btn"
          title="Connect a 3Dconnexion SpaceMouse (Chrome / Edge)"
          onClick={() => connect().catch(() => {})}
        >
          Connect SpaceMouse
        </button>
      )}
      {error && <span className="spacemouse-error muted">{error}</span>}
    </div>
  );
}