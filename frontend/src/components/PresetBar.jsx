import { useCallback, useEffect, useState } from "react";

import { deletePreset, listPresets, savePreset } from "../api.js";
import { INLINE_ERROR, MUTED, QUIET, ROW, SECONDARY_BUTTON } from "../styles.js";

/**
 * Saved settings for one service. Applying a preset fills the form below and is then
 * out of the way — nothing about a preset reaches the submitted job.
 */
export default function PresetBar({ service, settings, onApply }) {
  const [presets, setPresets] = useState([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setPresets(await listPresets(service));
    } catch (e) {
      // A preset list that cannot load must not take the form down with it.
      setError(e.detail || String(e));
    }
  }, [service]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function apply(id) {
    setSelected(id);
    setError(null);
    const preset = presets.find((entry) => entry.id === id);
    if (!preset) return;
    setName(preset.name);
    onApply(preset.settings);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await savePreset(service, name, settings);
      await refresh();
      setSelected(saved.id);
      setName(saved.name);
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deletePreset(service, selected);
      await refresh();
      setSelected("");
      setName("");
    } catch (e) {
      setError(e.detail || String(e));
    } finally {
      setBusy(false);
    }
  }

  const existing = presets.some((entry) => entry.name.toLowerCase() === name.trim().toLowerCase());

  return (
    <div className="flex flex-col gap-2 px-3.5 py-3 border border-line rounded-md bg-panel">
      <div className={ROW}>
        <span className="min-w-12 text-xs font-medium text-muted">Preset</span>
        <select
          className="max-w-[260px]"
          value={selected}
          onChange={(event) => apply(event.target.value)}
        >
          <option value="">
            {presets.length ? "Choose a saved setup…" : "No saved setups yet"}
          </option>
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={QUIET}
          disabled={!selected || busy}
          onClick={remove}
        >
          Delete
        </button>
      </div>

      <div className={ROW}>
        <input
          type="text"
          className="max-w-[260px]"
          value={name}
          maxLength={80}
          placeholder="Name this setup"
          onChange={(event) => setName(event.target.value)}
        />
        <button
          type="button"
          className={SECONDARY_BUTTON}
          disabled={!name.trim() || busy}
          onClick={save}
        >
          {existing ? "Save over" : "Save settings"}
        </button>
      </div>

      {error && <p className={INLINE_ERROR}>{error}</p>}
      <p className={MUTED}>
        A preset holds every option below, never the input. Applying one fills the form —
        change anything you like before starting.
      </p>
    </div>
  );
}
