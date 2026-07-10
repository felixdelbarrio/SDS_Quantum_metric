import type { CountryCode } from "./types";

const COUNTRY_TIMEZONES: Record<CountryCode, string> = {
  ES: "Europe/Madrid",
  CO: "America/Bogota",
  MX: "America/Mexico_City",
  AR: "America/Argentina/Buenos_Aires",
  PE: "America/Lima",
};

export function timezoneForCountry(country: CountryCode) {
  return COUNTRY_TIMEZONES[country];
}

export function todayInTimezone(timezone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${value.year}-${value.month}-${value.day}`;
}
