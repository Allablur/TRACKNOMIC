"use client";
import { useEffect, useState } from "react";
export function metric(value: number | null | undefined) {
  return value == null ? "Unavailable" : value.toLocaleString("en-US");
}
export async function request<T>(
  url: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1${url}`, { signal, cache: "no-store" });
  if (!response.ok)
    throw new Error(
      `Unable to load catalogue (HTTP ${response.status}). Check the API connection and retry.`,
    );
  return response.json() as Promise<T>;
}
export function useResource<T>(url: string | null) {
  const [attempt, setAttempt] = useState(0);
  const key = `${url}:${attempt}`;
  const [result, setResult] = useState<{
    key: string;
    data?: T;
    error?: string;
  }>({ key: "" });
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    request<T>(url, controller.signal)
      .then((data) => setResult({ key, data }))
      .catch((error) => {
        if (!controller.signal.aborted)
          setResult({
            key,
            error: error instanceof Error ? error.message : "Request failed",
          });
      });
    return () => controller.abort();
  }, [url, key]);
  return {
    data: result.key === key ? result.data : undefined,
    error: result.key === key ? result.error : undefined,
    loading: !!url && (result.key !== key || (!result.data && !result.error)),
    retry: () => setAttempt((n) => n + 1),
  };
}
