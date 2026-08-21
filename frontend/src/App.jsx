import { useEffect, useState } from "react";

import { SLIDES, getConfig, getHealth, getModels } from "./api.js";
import { usePolling } from "./usePolling.js";
import CurriculumForm from "./components/CurriculumForm.jsx";
import Header from "./components/Header.jsx";
import JobDetail from "./components/JobDetail.jsx";
import JobList from "./components/JobList.jsx";
import Sidebar from "./components/Sidebar.jsx";
import SlidesForm from "./components/SlidesForm.jsx";

export default function App() {
  const [activeTab, setActiveTab] = useState(SLIDES);
  // The service travels with the id: every job URL needs it.
  const [activeJob, setActiveJob] = useState(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState(null);
  const [metaError, setMetaError] = useState(null);

  const health = usePolling(getHealth, 15000, true);
  const ollamaDown = health.data?.ollama === "down";
  const ollamaUp = health.data?.ollama === "up";

  // /models is 503 while Ollama is down, so reload once it comes back.
  useEffect(() => {
    let cancelled = false;
    getConfig()
      .then((data) => !cancelled && setConfig(data))
      .catch((e) => !cancelled && setMetaError(e.detail || String(e)));
    getModels()
      .then((data) => {
        if (cancelled) return;
        setModels(data);
        setMetaError(null);
      })
      .catch((e) => !cancelled && setMetaError(e.detail || String(e)));
    return () => {
      cancelled = true;
    };
  }, [ollamaUp]);

  function openJob(job) {
    setActiveJob({ id: job.id, service: job.service });
    setActiveTab(job.service);
  }

  function submitted(job) {
    openJob(job);
    setRefreshToken((n) => n + 1);
  }

  function deleted(id) {
    setActiveJob((current) => (current?.id === id ? null : current));
    setRefreshToken((n) => n + 1);
  }

  function selectPipeline(service) {
    setActiveTab(service);
    setActiveJob(null);
  }

  const formProps = { config, models, ollamaDown, onSubmitted: submitted };

  return (
    <div className="app">
      <Header health={health.data} onRetry={health.refresh} />

      <div className="columns">
        <Sidebar active={activeTab} onSelect={selectPipeline} />

        <main className="workspace">
          {metaError && !ollamaDown && <p className="inline-error">{metaError}</p>}

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
        />
      </div>
    </div>
  );
}
