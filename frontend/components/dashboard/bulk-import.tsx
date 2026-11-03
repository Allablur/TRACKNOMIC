"use client";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Upload, LockKeyhole, CheckCircle2, Clock3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeading } from "@/components/layout/page-heading";
import {
  BulkBatch,
  ImportApiError,
  importRequest,
  parseArtists,
  MAX_FILE_BYTES,
} from "@/lib/bulk-import";
import { field, panel } from "./shared";
const savedKey = "trackonomics.spotify.bulk.batch";
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener("bulk-import-saved", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("bulk-import-saved", listener);
  };
}
function snapshot() {
  try {
    return localStorage.getItem(savedKey) || "";
  } catch {
    return "";
  }
}
function saveBatch(id: string) {
  try {
    if (id) localStorage.setItem(savedKey, id);
    else localStorage.removeItem(savedKey);
  } catch {}
  window.dispatchEvent(new Event("bulk-import-saved"));
}
function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Request failed. Please retry.";
}
const statuses = {
  pending: "Queued",
  running: "Importing",
  succeeded: "Imported",
  failed: "Failed",
  cancelled: "Cancelled",
};
export function BulkImportView() {
  const saved = useSyncExternalStore(subscribe, snapshot, () => "");
  const [tokenDraft, setTokenDraft] = useState("");
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [fileError, setFileError] = useState("");
  const [batchId, setBatchId] = useState("");
  const [reconnect, setReconnect] = useState("");
  const [batch, setBatch] = useState<BulkBatch | null>(null);
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const requestId = useRef<string | null>(null);
  const activeId = batchId || saved;
  const parsed = parseArtists(input);
  useEffect(() => {
    if (!token || !activeId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const data = await importRequest<BulkBatch>(
          `/${encodeURIComponent(activeId)}`,
          token,
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setBatch(data);
        setPollError("");
        if (data.status === "completed" || data.status === "cancelled") return;
      } catch (problem) {
        if (controller.signal.aborted) return;
        setPollError(message(problem));
        if (problem instanceof ImportApiError && problem.status === 401) {
          setToken("");
          return;
        }
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [token, activeId, reload]);
  async function unlock(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const value = tokenDraft.trim();
      await importRequest("/access", value);
      setToken(value);
      setTokenDraft("");
      setReload((n) => n + 1);
    } catch (problem) {
      setError(
        problem instanceof ImportApiError && problem.status === 404
          ? "Bulk imports are not available on this API yet. Deploy the latest API code, then try again."
          : message(problem),
      );
    } finally {
      setBusy(false);
    }
  }
  async function create() {
    if (!parsed.ids.length || parsed.errors.length) return;
    setBusy(true);
    setError("");
    requestId.current ??= crypto.randomUUID();
    try {
      const data = await importRequest<BulkBatch>("", token, {
        method: "POST",
        body: { request_id: requestId.current, artist_ids: parsed.ids },
      });
      setBatch(data);
      setBatchId(data.id);
      saveBatch(data.id);
      setReload((n) => n + 1);
    } catch (problem) {
      setError(message(problem));
    } finally {
      setBusy(false);
    }
  }
  async function control(action: "pause" | "resume" | "cancel" | "retry") {
    setBusy(true);
    setError("");
    try {
      const data = await importRequest<BulkBatch>(
        `/${encodeURIComponent(activeId)}/${action}`,
        token,
        { method: "POST" },
      );
      setBatch(data);
      setReload((n) => n + 1);
    } catch (problem) {
      setError(message(problem));
    } finally {
      setBusy(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    setFileError("");
    if (file.size > MAX_FILE_BYTES) {
      setFileError("Choose a CSV or text file smaller than 64 KB.");
      return;
    }
    try {
      setInput(await file.text());
      requestId.current = null;
    } catch {
      setFileError("Could not read that file. Try pasting the links instead.");
    }
  }
  const finished = batch
    ? batch.counts.succeeded + batch.counts.failed + batch.counts.cancelled
    : 0;
  return (
    <>
      <PageHeading
        title="Bulk import"
        description="Add real Spotify artists in one batch. Paste links or upload a CSV; we’ll handle the queue and waiting."
      />
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        {[
          [
            Upload,
            "Up to 100 artists",
            "Duplicates are removed before queuing.",
          ],
          [
            Clock3,
            "One at a time",
            "At least 60 seconds between artists; Spotify limits may add a wait.",
          ],
          [
            CheckCircle2,
            "Progress is saved",
            "Refresh or reconnect without restarting successful imports.",
          ],
        ].map(([Icon, title, text]) => {
          const Symbol = Icon as typeof Upload;
          return (
            <div key={title as string} className={panel}>
              <Symbol
                aria-hidden="true"
                size={20}
                className="mb-3 text-primary"
              />
              <h2 className="text-sm font-semibold">{title as string}</h2>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {text as string}
              </p>
            </div>
          );
        })}
      </div>
      {!token ? (
        <section className={`${panel} mb-6`}>
          <h2 className="mb-2 flex items-center gap-2 font-semibold">
            <LockKeyhole size={18} aria-hidden="true" />
            Unlock artist imports
          </h2>
          <p className="mb-5 max-w-2xl text-sm leading-6 text-muted-foreground">
            Use the INGESTION_TOKEN from your Render API’s environment settings.
            This is not your Spotify client secret. The token stays in memory
            for this page session and is not saved in browser storage.
          </p>
          <form onSubmit={unlock} className="flex flex-wrap items-end gap-3">
            <label className="grid min-w-0 flex-1 basis-64 gap-2 text-xs font-medium">
              Ingestion token
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={tokenDraft}
                onChange={(e) => setTokenDraft(e.target.value)}
                required
                className={field}
              />
            </label>
            <Button disabled={busy || !tokenDraft.trim()} type="submit">
              {busy ? "Checking…" : "Unlock imports"}
            </Button>
          </form>
          {saved && (
            <p className="mt-4 break-all text-xs text-muted-foreground">
              Saved batch: {saved}. Unlock to reconnect.
            </p>
          )}
        </section>
      ) : (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-white p-4">
          <p className="text-sm text-primary">
            Operator access unlocked for this page session.
          </p>
          <Button
            variant="outline"
            onClick={() => {
              setToken("");
              setTokenDraft("");
              setError("");
            }}
          >
            Lock screen
          </Button>
        </div>
      )}
      {error && (
        <p
          role="alert"
          className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {error}
        </p>
      )}
      {token && !activeId && (
        <section className={`${panel} mb-6`}>
          <h2 className="font-semibold">Choose your artists</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Paste one artist link, Spotify artist URI, or artist ID per line.
            CSV files can use an artist_id or spotify_url column; other columns
            are ignored. No JSON is needed.
          </p>
          <label className="mt-5 grid gap-2 text-sm font-medium">
            Artist links
            <textarea
              rows={7}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setFileError("");
                requestId.current = null;
              }}
              placeholder={
                "https://open.spotify.com/artist/…\nspotify:artist:…"
              }
              className={`${field} w-full font-mono`}
            />
          </label>
          <label className="mt-4 flex flex-wrap cursor-pointer items-center gap-2 rounded-lg border border-border p-3 text-sm">
            <Upload size={16} aria-hidden="true" />
            Upload CSV or text file
            <input
              className="w-full min-w-0 max-w-full text-xs"
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              onChange={(e) => void upload(e.target.files?.[0])}
            />
          </label>
          {fileError && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {fileError}
            </p>
          )}
          {input && (
            <div className="mt-4">
              <p role="status" className="text-sm font-medium">
                {parsed.ids.length} unique artists · {parsed.duplicates}{" "}
                duplicate rows removed
              </p>
              {parsed.errors.length > 0 && (
                <div
                  role="alert"
                  className="mt-3 rounded-lg bg-red-50 p-4 text-sm text-red-800"
                >
                  <p className="font-medium">Fix these rows before starting:</p>
                  <ul className="mt-2 max-h-48 list-disc overflow-y-auto pl-5">
                    {parsed.errors.map((problem, i) => (
                      <li key={i}>{problem}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          <Button
            className="mt-5"
            disabled={
              busy ||
              !parsed.ids.length ||
              parsed.errors.length > 0 ||
              !!fileError
            }
            onClick={() => void create()}
          >
            {busy
              ? "Creating batch…"
              : `Start import (${parsed.ids.length} artists)`}
          </Button>
          <p className="mt-3 text-xs text-muted-foreground">
            The API saves your queue and processes it in the background. On a
            free hosting plan, processing can pause while the API sleeps and
            resume when it wakes.
          </p>
        </section>
      )}
      {token && (
        <form
          className={`${panel} mb-6`}
          onSubmit={(e) => {
            e.preventDefault();
            if (
              !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
                reconnect.trim(),
              )
            ) {
              setError(
                "Enter the batch ID shown on this screen, not a Spotify artist ID.",
              );
              return;
            }
            setError("");
            setBatch(null);
            setBatchId(reconnect.trim());
            saveBatch(reconnect.trim());
            setReload((n) => n + 1);
          }}
        >
          <label className="grid gap-2 text-xs font-medium">
            Reconnect to a batch
            <input
              value={reconnect}
              onChange={(e) => setReconnect(e.target.value)}
              placeholder="Paste a saved batch ID"
              className={field}
            />
          </label>
          <Button
            variant="outline"
            className="mt-3"
            type="submit"
            disabled={!reconnect.trim() || busy}
          >
            Load batch
          </Button>
        </form>
      )}
      {pollError && token && (
        <div
          role="alert"
          className="mb-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm"
        >
          <p>{pollError}</p>
          <Button
            variant="outline"
            className="mt-3"
            onClick={() => setReload((n) => n + 1)}
          >
            Refresh progress
          </Button>
          {activeId && (
            <Button
              variant="outline"
              className="ml-3 mt-3"
              onClick={() => {
                setBatchId("");
                saveBatch("");
                setBatch(null);
                setPollError("");
              }}
            >
              Forget saved batch
            </Button>
          )}
        </div>
      )}
      {token && activeId && !batch && !pollError && (
        <p role="status" className={panel}>
          Loading saved batch…
        </p>
      )}
      {token && batch && (
        <section className={panel}>
          <div className="flex flex-wrap justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">{batch.name}</h2>
              <p className="mt-2 text-xs font-medium uppercase tracking-wide text-primary">
                Batch {batch.status}
              </p>
              <p className="mt-2 break-all text-xs text-muted-foreground">
                Batch ID:{" "}
                <span className="select-all font-mono">{batch.id}</span>
              </p>
            </div>
            <div className="flex flex-wrap items-start gap-2">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => setReload((n) => n + 1)}
              >
                Refresh progress
              </Button>
              {batch.status === "active" && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => void control("pause")}
                >
                  Pause queue
                </Button>
              )}
              {batch.status === "paused" && (
                <Button disabled={busy} onClick={() => void control("resume")}>
                  Resume queue
                </Button>
              )}
              {batch.counts.failed > 0 && batch.status !== "cancelled" && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => void control("retry")}
                >
                  Retry failed artists
                </Button>
              )}
              {(batch.status === "active" || batch.status === "paused") && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => void control("cancel")}
                >
                  Cancel remaining
                </Button>
              )}
            </div>
          </div>
          <label
            className="mt-6 block text-sm font-medium"
            htmlFor="import-progress"
          >
            {finished} of {batch.total} finished · {batch.counts.succeeded}{" "}
            imported · {batch.counts.failed} failed
          </label>
          <progress
            id="import-progress"
            value={finished}
            max={batch.total}
            className="mt-2 h-3 w-full accent-primary"
          />
          <p className="mt-3 text-sm text-muted-foreground">
            {batch.status === "active"
              ? `${batch.counts.pending} queued · ${batch.counts.running} importing. Requests run one at a time.`
              : batch.status === "paused"
                ? "Paused. Check any failed artist’s message, then resume or retry failed entries."
                : batch.status === "cancelled"
                  ? "Pending artists were cancelled. An already-running request can still finish."
                  : "Batch finished. Successful artists are available in your catalogue."}
          </p>
          {batch.status === "active" && batch.next_attempt_at && (
            <p className="mt-2 text-xs text-muted-foreground">
              Next queued attempt no earlier than{" "}
              {new Date(batch.next_attempt_at).toLocaleTimeString()}. Spotify
              may request an additional wait.
            </p>
          )}
          {!batch.worker_enabled && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              Background processing is disabled on the API server.
            </p>
          )}
          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="mb-4 text-left text-xs text-muted-foreground">
                Progress is saved on the server. Pause/cancel takes effect after
                any request already in progress.
              </caption>
              <thead>
                <tr>
                  {["Artist", "Status", "Attempts this cycle", "Details"].map(
                    (h) => (
                      <th key={h} className="p-3">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {batch.items.map((item) => (
                  <tr key={item.id} className="border-t border-border">
                    <th className="p-3 font-medium">
                      <a
                        className="text-primary underline underline-offset-2"
                        href={`https://open.spotify.com/artist/${item.spotify_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {item.name || item.spotify_id}
                      </a>
                    </th>
                    <td className="p-3">{statuses[item.status]}</td>
                    <td className="p-3">{item.attempts}</td>
                    <td className="max-w-sm p-3 text-xs leading-5">
                      {item.error || ""}
                      {item.artist_id && (
                        <Link
                          className="text-primary underline"
                          href={`/artists/${item.artist_id}`}
                        >
                          View artist
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(batch.status === "completed" || batch.status === "cancelled") && (
            <Button
              className="mt-5"
              variant="outline"
              onClick={() => {
                saveBatch("");
                setBatchId("");
                setBatch(null);
                setInput("");
                setPollError("");
                requestId.current = null;
              }}
            >
              Create another batch
            </Button>
          )}
        </section>
      )}
    </>
  );
}
