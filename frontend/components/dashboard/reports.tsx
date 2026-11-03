"use client";
import { useState } from "react";
import { PageHeading } from "@/components/layout/page-heading";
import { Button } from "@/components/ui/button";
import { FilterBar, Notice, panel, useFilters } from "./shared";
export function ReportsView() {
  const [filters, setFilters] = useFilters();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function download(format: "csv" | "pdf") {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const response = await fetch("/api/v1/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...filters, format }),
      });
      if (!response.ok) {
        const problem = await response
          .json()
          .catch(() => ({ detail: "Report generation failed" }));
        throw new Error(
          typeof problem.detail === "string"
            ? problem.detail
            : `Report failed (HTTP ${response.status})`,
        );
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `trackonomics-catalogue.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess(`${format.toUpperCase()} report downloaded.`);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Report failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        title="Analytical reports"
        description="Export your filtered artist catalogue, with source attribution and explicit metric availability."
      />
      <Notice />
      <FilterBar
        onApply={(value) => {
          setFilters(value);
          setSuccess("");
        }}
      />
      <section className={panel}>
        <h2 className="text-lg font-semibold">Catalogue export</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          Applied filters: source {filters.provider}; artist{" "}
          {filters.q || "all"}; country {filters.country || "all"}. CSV includes
          catalogue counts and metric capture metadata. PDF adds a catalogue
          summary, genre representation, and dated release activity.
        </p>
        <p className="mt-3 text-xs text-muted-foreground">
          Audience metrics remain blank in CSV and unavailable in PDF when
          absent. Limits: 10,000 artists per CSV, 500 per PDF. Narrow filters
          for larger catalogues.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button disabled={busy} onClick={() => download("csv")}>
            Download CSV
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => download("pdf")}
          >
            Download PDF
          </Button>
        </div>
        {busy && (
          <p role="status" className="mt-4 text-sm">
            Generating report…
          </p>
        )}
        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}
        {success && (
          <p role="status" className="mt-4 text-sm text-primary">
            {success}
          </p>
        )}
      </section>
    </>
  );
}
