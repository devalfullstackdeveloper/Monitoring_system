import { useEffect, useState } from "react";
import { screenshotImageUrl } from "../api";

export default function useScreenshotImageUrls(screenshots) {
  const [imageUrls, setImageUrls] = useState({});

  useEffect(() => {
    let cancelled = false;
    const createdUrls = [];
    setImageUrls({});

    Promise.all(screenshots.map(async (screenshot) => {
      try {
        const url = await screenshotImageUrl(screenshot.id);
        if (cancelled) {
          URL.revokeObjectURL(url);
          return [screenshot.id, null];
        }
        createdUrls.push(url);
        return [screenshot.id, url];
      } catch {
        return [screenshot.id, null];
      }
    })).then((entries) => {
      if (!cancelled) setImageUrls(Object.fromEntries(entries));
    });

    return () => {
      cancelled = true;
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [screenshots]);

  return imageUrls;
}