import { useEffect, useState } from "react";

import { SLIDES, getConfig, getHealth, getModels } from "./api.js";
import { usePolling } from "./usePolling.js";
import CurriculumForm from "./components/CurriculumForm.jsx";
import Header from "./components/Header.jsx";
import JobDetail from "./components/JobDetail.jsx";
import JobList from "./components/JobList.jsx";
import Sidebar from "./components/Sidebar.jsx";
import SlidesForm from "./components/SlidesForm.jsx";
import { INLINE_ERROR } from "./styles.js";

export default function App() {
  const [activeTab, setActiveTab] = useState(SLIDES);
  // The service travels with the id: every job URL needs it.
  const [activeJob, setActiveJob] = useState(null);
  const [refreshToken, setRefreshToken] = useState(0);
  // Ids the rail flashes once. Cleared straight after, because a row remounts when its
  // job changes group, and a highlight that never expired would replay on every move.
  const [created, setCreated] = useState([]);
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState(null);
  // One state for both would let whichever request finishes second clear the other
  // one's failure, leaving a form stuck on "Loading configuration…" with no reason.
  const [configError, setConfigError] = useState(null);
  const [modelsError, setModelsError] = useState(null);
  const [attempt, setAttempt] = useState(0);

  const health = usePolling(getHealth, 15000, true);
  const ollamaDown = health.data?.ollama === "down";
  const ollamaUp = health.data?.ollama === "up";

  // /models is 503 while Ollama is down, so reload once it comes back.
  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((data) => {
        if (cancelled) return;
        setConfig(data);
        setConfigError(null);
      })
      .catch((e) => !cancelled && setConfigError(e.detail || String(e)));
    getModels()
      .then((data) => {
        if (cancelled) return;
        setModels(data);
        setModelsError(null);
      })
      .catch((e) => !cancelled && setModelsError(e.detail || String(e)));
    return () => {
      cancelled = true;
    };
  }, [ollamaUp, attempt]);

  function openJob(job) {
    setActiveJob({ id: job.id, service: job.service });
    setActiveTab(job.service);
  }

  // `open` is the submitter's call, not a count: one deck that succeeded should land on
  // its job, but a batch — or a batch that partly failed — has to leave the form up,
  // because the per-file errors are only rendered there.
  function submitted(jobs, open) {
    setCreated(jobs.map((job) => job.id));
    if (open && jobs.length > 0) openJob(jobs[0]);
    setRefreshToken((n) => n + 1);
  }

  function deleted(id) {
    setActiveJob((current) => (current?.id === id ? null : current));
    setRefreshToken((n) => n + 1);
  }

  useEffect(() => {
    if (created.length === 0) return undefined;
    // Long enough to cover the rail's immediate refetch plus the animation, short
    // enough that no job has changed status yet.
    const timer = setTimeout(() => setCreated([]), 2000);
    return () => clearTimeout(timer);
  }, [created]);

  function selectPipeline(service) {
    setActiveTab(service);
    setActiveJob(null);
  }

  const reloadMeta = () => setAttempt((n) => n + 1);

  const formProps = {
    config, models, ollamaDown, configError, onRetryMeta: reloadMeta, onSubmitted: submitted,
  };

  return (
    <div className="flex flex-col h-full max-rail:h-auto max-rail:min-h-full">
      <Header health={health.data} onRetry={health.refresh} />

      <div className="flex-1 min-h-0 grid grid-cols-[180px_minmax(600px,1fr)_310px] max-rail:grid-cols-1">
        <Sidebar active={activeTab} onSelect={selectPipeline} />

        <main className="overflow-y-auto min-h-0 max-rail:overflow-y-visible bg-panel px-6 pt-5 pb-10">
          {/* While Ollama is down the header banner already says so; a second copy of
              the same 503 in the workspace is noise. */}
          {modelsError && !ollamaDown && (
            <p className={INLINE_ERROR}>Model list unavailable — {modelsError}</p>
          )}

          {activeJob ? (
            // Keyed so switching jobs resets the detail rather than briefly showing
            // the previous job's data under the new job's header.
            <JobDetail
              key={activeJob.id}
              id={activeJob.id}
              service={activeJob.service}
              onDeleted={deleted}
            />
          ) : activeTab === SLIDES ? (
            <SlidesForm {...formProps} />
          ) : (
            <CurriculumForm {...formProps} />
          )}
        </main>

        <JobList
          activeJobId={activeJob?.id}
          onSelect={openJob}
          refreshToken={refreshToken}
          createdIds={created}
        />
      </div>
    </div>
  );
}
