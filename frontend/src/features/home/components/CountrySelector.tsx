import { AvailableCountry, CountryCode } from "../types";

type Props = {
  countries: AvailableCountry[];
  value: CountryCode;
  onChange: (country: CountryCode) => void;
};

export function CountrySelector({ countries, value, onChange }: Props) {
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
    </label>
  );
}
