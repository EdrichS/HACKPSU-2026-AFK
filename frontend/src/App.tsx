import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { glassesUserRoutes } from "./flows/glasses-user/routes";
import { visitorRoutes } from "./flows/visitor/routes";
import { LiveView } from "./hud/LiveView";
import { HomePage } from "./pages/HomePage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        {visitorRoutes}
        {glassesUserRoutes}
        <Route path="/live" element={<LiveView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
