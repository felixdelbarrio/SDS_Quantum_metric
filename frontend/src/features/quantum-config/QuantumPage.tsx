import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, ShieldCheck, Wifi } from "lucide-react";
import { FormEvent, useState } from "react";
import { apiGet, apiPost, apiPut } from "../../shared/api/client";

type QuantumConfig = {
  browser: "chrome" | "edge" | "safari" | "firefox";
  base_url: string;
  session_mode: "browser" | "manual";
  country: "ES" | "MX" | "PE" | "CO" | "AR";
  dashboard_url: string;
  verify_tls: boolean;
};

type ConnectionState = {
  status: "not_tested" | "ok" | "ko";
  endpoint_tested?: string;
  latency_ms?: number;
  timestamp?: string;
  message: string;
  error?: string;
};

export function QuantumPage() {
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: ["quantum-config"],
    queryFn: () => apiGet<QuantumConfig>("/config/quantum"),
  });
  const [form, setForm] = useState<QuantumConfig | null>(null);
  const [manualCookie, setManualCookie] = useState("");

  const current = form ?? config.data;

  const save = useMutation({
    mutationFn: (payload: QuantumConfig & { manual_cookie?: string }) =>
      apiPut<QuantumConfig>("/config/quantum", payload),
    onSuccess: (data) => {
      setForm(data);
      setManualCookie("");
      void queryClient.invalidateQueries({ queryKey: ["quantum-config"] });
    },
  });

  const test = useMutation({
    mutationFn: () => apiPost<ConnectionState>("/quantum/test-connection"),
  });

  function update<K extends keyof QuantumConfig>(
    key: K,
    value: QuantumConfig[K],
  ) {
    if (!current) return;
    setForm({ ...current, [key]: value });
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!current) return;
    save.mutate({
      ...current,
      manual_cookie:
        current.session_mode === "manual" ? manualCookie : undefined,
    });
  }

  if (!current) return <div className="empty">Cargando</div>;

  return (
    <>
      <header className="page-header">
        <h1>Quantum</h1>
        <span className={`status ${test.data?.status ?? "not_tested"}`}>
          {test.data?.status ?? "not_tested"}
        </span>
      </header>

      <form className="card grid" onSubmit={onSubmit}>
        <div className="toolbar">
          <label className="field">
            <span>Browser</span>
            <select
              value={current.browser}
              onChange={(event) =>
                update(
                  "browser",
                  event.target.value as QuantumConfig["browser"],
                )
              }
            >
              <option value="chrome">Chrome</option>
              <option value="edge">Edge</option>
              <option value="safari">Safari</option>
              <option value="firefox">Firefox</option>
            </select>
          </label>
          <label className="field">
            <span>Session mode</span>
            <select
              value={current.session_mode}
              onChange={(event) =>
                update(
                  "session_mode",
                  event.target.value as QuantumConfig["session_mode"],
                )
              }
            >
              <option value="browser">Browser</option>
              <option value="manual">Manual</option>
            </select>
          </label>
          <label className="field">
            <span>Pais</span>
            <select
              value={current.country}
              onChange={(event) =>
                update(
                  "country",
                  event.target.value as QuantumConfig["country"],
                )
              }
            >
              <option value="ES">Espana</option>
              <option value="MX">Mexico</option>
              <option value="PE">Peru</option>
              <option value="CO">Colombia</option>
              <option value="AR">Argentina</option>
            </select>
          </label>
        </div>
        <label className="field">
          <span>Base URL</span>
          <input
            value={current.base_url}
            onChange={(event) => update("base_url", event.target.value)}
          />
        </label>
        <label className="field">
          <span>Dashboard URL</span>
          <input
            value={current.dashboard_url}
            onChange={(event) => update("dashboard_url", event.target.value)}
          />
        </label>
        {current.session_mode === "manual" && (
          <label className="field">
            <span>Cookie manual</span>
            <textarea
              value={manualCookie}
              onChange={(event) => setManualCookie(event.target.value)}
              autoComplete="off"
            />
          </label>
        )}
        <div className="toolbar">
          <button className="button" type="submit" disabled={save.isPending}>
            <Save size={16} /> Guardar
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={() => test.mutate()}
            disabled={test.isPending}
          >
            <Wifi size={16} /> Test
          </button>
        </div>
      </form>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="toolbar">
          <ShieldCheck size={18} />
          <strong>{test.data?.message ?? "No probado"}</strong>
        </div>
        {test.data?.endpoint_tested && <p>{test.data.endpoint_tested}</p>}
        {test.data?.latency_ms && <p>{test.data.latency_ms} ms</p>}
        {test.data?.error && <p>{test.data.error}</p>}
      </section>
    </>
  );
}
