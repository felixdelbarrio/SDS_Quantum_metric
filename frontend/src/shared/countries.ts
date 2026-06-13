export type CountryCode = "ES" | "MX" | "CO" | "AR" | "PE";

export const COUNTRY_OPTIONS: Array<{ code: CountryCode; label: string }> = [
  { code: "ES", label: "Espana" },
  { code: "MX", label: "Mexico" },
  { code: "CO", label: "Colombia" },
  { code: "AR", label: "Argentina" },
  { code: "PE", label: "Peru" },
];

export function countryLabel(code: string) {
  return (
    COUNTRY_OPTIONS.find((country) => country.code === code)?.label ?? code
  );
}
