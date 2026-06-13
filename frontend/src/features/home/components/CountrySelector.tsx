import { Database, DatabaseZap } from "lucide-react";
import { AvailableCountry, CountryCode } from "../types";

type Props = {
  countries: AvailableCountry[];
  value: CountryCode;
  onChange: (country: CountryCode) => void;
};

export function CountrySelector({ countries, value, onChange }: Props) {
  const selected = countries.find((country) => country.code === value);

  return (
    <label className="command-field">
      <span>Pais</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as CountryCode)}
        aria-label="Pais del dashboard"
        disabled={!countries.length}
      >
        {countries.length ? (
          countries.map((country) => (
            <option key={country.code} value={country.code}>
              {country.label}
            </option>
          ))
        ) : (
          <option value={value}>Sin datos</option>
        )}
      </select>
      <span className={`data-badge ${selected?.has_data ? "ok" : ""}`}>
        {selected?.has_data ? (
          <DatabaseZap size={14} aria-hidden="true" />
        ) : (
          <Database size={14} aria-hidden="true" />
        )}
        {selected?.has_data
          ? `${selected.raw_calls} calls / ${selected.rows} filas`
          : "Sin Parquet"}
      </span>
    </label>
  );
}
