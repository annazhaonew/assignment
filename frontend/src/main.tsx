import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import RunWorkflow from "./pages/RunWorkflow";
import Library from "./pages/Library";
import PublishWorkflow from "./pages/PublishWorkflow";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/run" replace />} />
          <Route path="/run" element={<RunWorkflow />} />
          <Route path="/library" element={<Library />} />
          <Route path="/publish" element={<PublishWorkflow />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
