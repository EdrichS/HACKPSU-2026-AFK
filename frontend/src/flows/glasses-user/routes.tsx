import type { ReactNode } from "react";
import { Navigate, Outlet, Route } from "react-router";

import { AllSetScreen } from "./AllSetScreen";
import { ContextScreen } from "./ContextScreen";
import { GlassesUserVoiceScreen } from "./GlassesUserVoiceScreen";
import { NameScreen } from "./NameScreen";
import { GlassesUserFlowProvider, useGlassesUserFlow } from "./state";

function Step({ need, children }: { need: "name" | "done"; children: ReactNode }) {
  const flow = useGlassesUserFlow();
  if (need === "done") return flow.doneName ? children : <Navigate to="/setup" replace />;
  return flow.name.trim() ? children : <Navigate to="/setup" replace />;
}

export const glassesUserRoutes = (
  <Route
    path="/setup"
    element={
      <GlassesUserFlowProvider>
        <Outlet />
      </GlassesUserFlowProvider>
    }
  >
    <Route index element={<NameScreen />} />
    <Route path="context" element={<Step need="name"><ContextScreen /></Step>} />
    <Route path="voice" element={<Step need="name"><GlassesUserVoiceScreen /></Step>} />
    <Route path="done" element={<Step need="done"><AllSetScreen /></Step>} />
  </Route>
);
