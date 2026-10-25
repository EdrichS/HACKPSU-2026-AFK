import { Route } from "react-router";

import { FacesScreen } from "./FacesScreen";
import { PeopleScreen } from "./PeopleScreen";
import { PersonScreen } from "./PersonScreen";

/** The manage area: every person and everything stored about them, with the API as the only state. */
export const manageRoutes = (
  <Route path="/manage">
    <Route index element={<PeopleScreen />} />
    <Route path="people/:id" element={<PersonScreen />} />
    <Route path="faces" element={<FacesScreen />} />
  </Route>
);
