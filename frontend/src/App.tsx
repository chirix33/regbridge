import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ScopePage } from "./pages/ScopePage";
import { HeadingCasePage } from "./pages/HeadingCasePage";
import { EvaluationDashboard } from "./pages/EvaluationDashboard";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 60_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ScopePage />} />
          <Route path="/demo/case-a" element={<HeadingCasePage />} />
          <Route path="/demo/case-b" element={<HeadingCasePage />} />
          <Route path="/demo/case-c" element={<HeadingCasePage />} />
          <Route path="/evaluation" element={<EvaluationDashboard />} />
          <Route path="/case-a" element={<Navigate to="/demo/case-a" replace />} />
          <Route path="/case-b" element={<Navigate to="/demo/case-b" replace />} />
          <Route path="/case-c" element={<Navigate to="/demo/case-c" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
