import { Image as ImageIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { useApiConfig } from "../features/settings/settingsStore";
import { useBlobObjectUrl } from "./useBlobObjectUrl";

type FoodImageProps = {
  alt: string;
  className?: string;
  fit?: "contain" | "cover";
  src?: string | null;
};

const protectedImagePathFromSrc = (src?: string | null) => {
  if (!src) {
    return null;
  }
  try {
    const path = src.startsWith("/")
      ? src
      : src.startsWith("http://") || src.startsWith("https://")
        ? new URL(src).pathname
        : "";
    if (path.match(/^\/photos\/[^/]+\/file$/)) {
      return path;
    }
    if (path.match(/^\/products\/[^/]+\/image\/file$/)) {
      return path;
    }
    return null;
  } catch {
    return null;
  }
};

export function FoodImage({
  alt,
  className = "h-12 w-12",
  fit = "contain",
  src,
}: FoodImageProps) {
  const config = useApiConfig();
  const [failed, setFailed] = useState(false);
  const protectedImagePath = protectedImagePathFromSrc(src);
  const protectedImage = useQuery({
    queryKey: [
      "food-image-protected-file",
      protectedImagePath,
      config.baseUrl,
      config.token,
    ],
    queryFn: async () => {
      if (!protectedImagePath) {
        throw new Error("No protected image path.");
      }
      return apiClient.getImageFile(config, protectedImagePath);
    },
    enabled: Boolean(protectedImagePath && config.token.trim()),
  });
  const protectedObjectUrl = useBlobObjectUrl(protectedImage.data);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  const imageSrc = protectedImagePath ? protectedObjectUrl : src;
  const imageFailed =
    failed || (protectedImagePath ? protectedImage.isError : false);

  if (!imageSrc || imageFailed) {
    return (
      <span
        aria-label="изображение недоступно"
        className={`flex items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--muted)] ${className}`}
        role="img"
      >
        <ImageIcon size={18} strokeWidth={1.6} />
      </span>
    );
  }

  return (
    <img
      alt={alt}
      className={`border border-[var(--hairline)] bg-[var(--surface)] ${
        fit === "cover" ? "object-cover" : "object-contain"
      } ${className}`}
      loading="lazy"
      onError={() => setFailed(true)}
      src={imageSrc}
    />
  );
}
