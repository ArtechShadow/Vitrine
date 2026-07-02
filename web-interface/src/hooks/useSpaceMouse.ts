import { useCallback, useEffect, useRef, useState } from "react";
import {
  spaceMouseDriver,
  type SpaceMouseMotion,
  type SpaceMouseMotionListener,
} from "../lib/spacemouse";

export function useSpaceMouse(onMotion?: SpaceMouseMotionListener) {
  const [connected, setConnected] = useState(spaceMouseDriver.connected);
  const [deviceName, setDeviceName] = useState<string | null>(spaceMouseDriver.deviceName);
  const [error, setError] = useState<string | null>(null);
  const onMotionRef = useRef(onMotion);
  onMotionRef.current = onMotion;

  useEffect(() => {
    const sync = () => {
      setConnected(spaceMouseDriver.connected);
      setDeviceName(spaceMouseDriver.deviceName);
    };
    const unsubMotion = spaceMouseDriver.subscribe((motion) => {
      onMotionRef.current?.(motion);
    });
    void spaceMouseDriver.reconnect().then((name) => {
      if (name) sync();
    }).catch(() => {});
    return () => unsubMotion();
  }, []);

  const connect = useCallback(async () => {
    setError(null);
    try {
      const name = await spaceMouseDriver.connect();
      setConnected(true);
      setDeviceName(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect SpaceMouse");
      throw e;
    }
  }, []);

  const disconnect = useCallback(async () => {
    await spaceMouseDriver.disconnect();
    setConnected(false);
    setDeviceName(null);
  }, []);

  return {
    supported: spaceMouseDriver.supported,
    connected,
    deviceName,
    error,
    connect,
    disconnect,
  };
}

export type { SpaceMouseMotion };