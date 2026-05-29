import { Navigate, createBrowserRouter } from "react-router-dom";

import { ConsolePage } from "../pages/ConsolePage";
import { EvalPage } from "../pages/EvalPage";
import { TraceDetailPage } from "../pages/TraceDetailPage";
import { TraceListPage } from "../pages/TraceListPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/console" replace /> },
  { path: "/console", element: <ConsolePage /> },
  { path: "/traces", element: <TraceListPage /> },
  { path: "/traces/:traceId", element: <TraceDetailPage /> },
  { path: "/evals", element: <EvalPage /> }
]);
