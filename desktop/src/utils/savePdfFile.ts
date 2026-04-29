import { isTauri } from "@tauri-apps/api/core";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";

export async function savePdfFile({
  bytes,
  defaultPath,
}: {
  bytes: Uint8Array;
  defaultPath: string;
}) {
  if (!isTauri()) {
    throw new Error("Сохранение PDF доступно в Tauri-приложении.");
  }

  const selectedPath = await save({
    defaultPath,
    filters: [{ name: "PDF", extensions: ["pdf"] }],
    title: "Сохранить отчёт для врача",
  });

  if (!selectedPath) {
    return null;
  }

  const targetPath = selectedPath.toLowerCase().endsWith(".pdf")
    ? selectedPath
    : `${selectedPath}.pdf`;
  await writeFile(targetPath, bytes);
  return targetPath;
}
