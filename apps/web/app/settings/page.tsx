"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  getActiveStrategy,
  getStrategyPresets,
  saveStrategy,
  seedDefaults,
  type StrategyConfig,
} from "@/lib/api";

export default function SettingsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [active, setActive] = useState<StrategyConfig | null>(null);
  const [presets, setPresets] = useState<{ name: string; payload: Record<string, unknown> }[]>([]);
  const [selectedName, setSelectedName] = useState("balanced");
  const [json, setJson] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    async function load() {
      try {
        const [p, a] = await Promise.all([
          getStrategyPresets(),
          getActiveStrategy("balanced"),
        ]);
        setPresets(p.presets);
        const merged = a?.payload ?? p.presets.find((x) => x.name === "balanced")?.payload ?? {};
        setJson(JSON.stringify(merged, null, 2));
        if (a) setActive(a);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "failed to load");
      }
    }
    load();
  }, [user]);

  async function onLoadPreset(name: string) {
    setSelectedName(name);
    const p = presets.find((x) => x.name === name);
    if (p) setJson(JSON.stringify(p.payload, null, 2));
  }

  async function onSave(activate: boolean) {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const payload = JSON.parse(json);
      const r = await saveStrategy({ name: selectedName, payload, activate });
      setActive(r);
      setSaved(`Saved v${r.version}${activate ? " (active)" : ""}.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSeed() {
    setBusy(true);
    setError(null);
    try {
      const r = await seedDefaults();
      setSaved(`Seeded ${r.seeded.length} preset configs (inactive v1 rows).`);
      const a = await getActiveStrategy("balanced");
      if (a) {
        setActive(a);
        setJson(JSON.stringify(a.payload, null, 2));
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "seed failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="p-6 max-w-4xl mx-auto flex flex-col gap-4">
      <h1 className="text-lg font-semibold">Strategy settings</h1>

      <section className="rounded-md border border-border bg-panel p-4 flex flex-col gap-3 text-xs">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Active config</h2>
            <p className="text-muted">
              {active
                ? `Version ${active.version} · ${new Date(active.created_at).toLocaleString()}`
                : "No active config — defaults from the bundled preset are used at runtime."}
            </p>
          </div>
          <button
            onClick={onSeed}
            disabled={busy}
            className="px-3 py-1.5 rounded border border-border text-muted hover:text-primary"
          >
            Seed presets
          </button>
        </div>
      </section>

      <section className="rounded-md border border-border bg-panel p-4 flex flex-col gap-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-muted">Presets:</span>
          {presets.map((p) => (
            <button
              key={p.name}
              onClick={() => onLoadPreset(p.name)}
              className={`px-2 py-1 rounded border ${
                selectedName === p.name
                  ? "border-info text-info"
                  : "border-border text-muted hover:text-primary"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
        <label className="flex flex-col gap-1 text-muted">
          Config JSON
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            className="font-mono text-[11px] h-96 bg-bg border border-border rounded p-2 text-primary"
            spellCheck={false}
          />
        </label>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onSave(true)}
            disabled={busy}
            className="px-3 py-1.5 rounded border border-info text-info hover:bg-info/20 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save & activate"}
          </button>
          <button
            onClick={() => onSave(false)}
            disabled={busy}
            className="px-3 py-1.5 rounded border border-border text-muted hover:text-primary"
          >
            Save as draft
          </button>
          {saved && <span className="text-bullish">{saved}</span>}
          {error && <span className="text-bearish">{error}</span>}
        </div>
      </section>
    </main>
  );
}
