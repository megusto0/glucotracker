const pad2 = (value: number) => value.toString().padStart(2, "0");

export const toLocalDateTimeString = (date: Date) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(
    date.getDate(),
  )}T${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(
    date.getSeconds(),
  )}`;

export const localDateBoundaryString = (value: string, endOfDay: boolean) => {
  if (!value) {
    return undefined;
  }
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return undefined;
  }
  const date = endOfDay
    ? new Date(year, month - 1, day, 23, 59, 59)
    : new Date(year, month - 1, day, 0, 0, 0);
  return toLocalDateTimeString(date);
};

export const localDateTimeBefore = (iso: string) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return toLocalDateTimeString(new Date(date.getTime() - 1));
};
