const nicotineUnits = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 2,
});

export function formatNicotineUnits(value: number) {
  return nicotineUnits.format(value);
}
