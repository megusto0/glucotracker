import { isTauri } from "@tauri-apps/api/core";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";

export async function saveTextFile({
  defaultPath,
  text,
  title = "Сохранить текстовый файл",
}: {
  defaultPath: string;
  text: string;
  title?: string;
}) {
  if (!isTauri()) {
    throw new Error("Сохранение TXT доступно в Tauri-приложении.");
  }

  const selectedPath = await save({
    defaultPath,
    filters: [{ name: "Text", extensions: ["txt"] }],
    title,
  });

  if (!selectedPath) {
    return null;
  }

  const targetPath = selectedPath.toLowerCase().endsWith(".txt")
    ? selectedPath
    : `${selectedPath}.txt`;
  const encoded = new TextEncoder().encode(text);
  const bytes = new Uint8Array(encoded.length + 3);
  bytes.set([0xef, 0xbb, 0xbf], 0);
  bytes.set(encoded, 3);
  await writeFile(targetPath, bytes);
  return targetPath;
}
