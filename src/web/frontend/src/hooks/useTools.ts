// Capability discovery for feature gating.
//
// Panels whose backend endpoints Vitrine deliberately does not build (energy,
// experimental branches, per-stage job controls) are hidden unless /api/tools
// reports them. A missing or failing /api/tools simply means "nothing optional
// is available" — the core loop keeps working.

import { useEffect, useState } from "react";
import { getTools, type ToolStatus } from "../api/client";

export interface ToolsState {
  tools: ToolStatus | null;
  loading: boolean;
  /** True when the tools endpoint itself is unavailable (degrade gracefully). */
  unavailable: boolean;
}

export function useTools(): ToolsState {
  const [state, setState] = useState<ToolsState>({ tools: null, loading: true, unavailable: false });

  useEffect(() => {
    let active = true;
    getTools()
      .then((tools) => active && setState({ tools, loading: false, unavailable: false }))
      .catch(() => active && setState({ tools: null, loading: false, unavailable: true }));
    return () => {
      active = false;
    };
  }, []);

  return state;
}

/** Read a boolean capability flag defensively. */
export function hasFeature(tools: ToolStatus | null, key: string): boolean {
  if (!tools) return false;
  if (tools.features && key in tools.features) return Boolean(tools.features[key]);
  const direct = (tools as unknown as Record<string, { available?: boolean } | undefined>)[key];
  return Boolean(direct?.available);
}
