import { useQuery } from "@tanstack/react-query";
import { RefreshCcw } from "lucide-react";
import { apiGet } from "../../shared/api/client";

type Summary = {
  raw_calls: number;
  countries: string[];
  rows: number;
  cards: number;
};

export function HomePage() {
  const summary = useQuery({
    queryKey: ["analytics-summary"],
    queryFn: () => apiGet<Summary>("/analytics/summary"),
  });

  const data = summary.data;

  return (
    <>
      <header className="page-header">
        <h1>Dashboard local</h1>
        <button
          className="button secondary"
          onClick={() => void summary.refetch()}
        >
          <RefreshCcw size={16} /> Actualizar
        </button>
      </header>

      <section className="grid cols-3">
        <div className="card kpi">
          <span>Raw calls</span>
          <strong>{data?.raw_calls ?? "0"}</strong>
        </div>
        <div className="card kpi">
          <span>Filas recibidas</span>
          <strong>{data?.rows ?? "0"}</strong>
        </div>
        <div className="card kpi">
          <span>Cards</span>
          <strong>{data?.cards ?? "0"}</strong>
        </div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        {data && data.raw_calls > 0 ? (
          <table className="table">
            <tbody>
              <tr>
                <th>Paises</th>
                <td>{data.countries.join(", ")}</td>
              </tr>
              <tr>
                <th>Origen</th>
                <td>Parquet local</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <div className="empty">Sin datos locales</div>
        )}
      </section>
    </>
  );
}
