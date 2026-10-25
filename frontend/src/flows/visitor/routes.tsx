import type { ReactNode } from "react";
import { Navigate, Outlet, Route } from "react-router";

import { AboutYouScreen } from "./AboutYouScreen";
import { ConsentScreen } from "./ConsentScreen";
import { FacePhotosScreen } from "./FacePhotosScreen";
import { IntroScreen } from "./IntroScreen";
import { VisitorFlowProvider, useVisitorFlow } from "./state";
import { ThankYouScreen } from "./ThankYouScreen";
import { VisitorVoiceScreen } from "./VisitorVoiceScreen";

/** A step opened without the earlier steps done (a reload, a typed URL) goes back to the first open one. */
function Step({ need, children }: { need: "consent" | "photos" | "voice" | "submitted"; children: ReactNode }) {
  const flow = useVisitorFlow();
  if (need === "submitted") return flow.submitted ? children : <Navigate to="/visitor" replace />;
  if (!flow.consent) return <Navigate to="/visitor" replace />;
  if ((need === "photos" || need === "voice") && flow.photos.length < 5) return <Navigate to="/visitor/photos" replace />;
  if (need === "voice" && !flow.voice) return <Navigate to="/visitor/voice" replace />;
  return children;
}

export const visitorRoutes = (
  <Route
    path="/visitor"
    element={
      <VisitorFlowProvider>
        <Outlet />
      </VisitorFlowProvider>
    }
  >
    <Route index element={<IntroScreen />} />
    <Route path="consent" element={<ConsentScreen />} />
    <Route path="photos" element={<Step need="consent"><FacePhotosScreen /></Step>} />
    <Route path="voice" element={<Step need="photos"><VisitorVoiceScreen /></Step>} />
    <Route path="about" element={<Step need="voice"><AboutYouScreen /></Step>} />
    <Route path="thanks" element={<Step need="submitted"><ThankYouScreen /></Step>} />
  </Route>
);
