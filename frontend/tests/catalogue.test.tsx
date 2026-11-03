import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SourceLinks } from "@/components/dashboard/source-links";
import { metric } from "@/lib/api";
import {
  FilterBar,
  DataState,
  Pagination,
} from "@/components/dashboard/shared";

describe("Catalogue data and controls", () => {
  it("attributes Spotify metadata with a source link", () => {
    render(
      <SourceLinks
        sources={[
          {
            provider: "spotify",
            external_id: "A".repeat(22),
            url: "https://open.spotify.com/artist/" + "A".repeat(22),
          },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: /Spotify/ })).toHaveAttribute(
      "href",
      "https://open.spotify.com/artist/" + "A".repeat(22),
    );
  });
  it("never renders an arbitrary provider URL as a link", () => {
    render(
      <SourceLinks
        sources={[
          {
            provider: "spotify",
            external_id: "test",
            url: "javascript:alert(1)",
          },
        ]}
      />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("preserves unknown metrics and real zeros", () => {
    expect(metric(null)).toBe("Unavailable");
    expect(metric(undefined)).toBe("Unavailable");
    expect(metric(0)).toBe("0");
    expect(metric(1200)).toBe("1,200");
  });
  it("submits search and provider filters", () => {
    const apply = vi.fn();
    render(<FilterBar onApply={apply} />);
    fireEvent.change(screen.getByLabelText("Search artist"), {
      target: { value: "Velvet" },
    });
    fireEvent.change(screen.getByLabelText("Source"), {
      target: { value: "spotify" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(apply).toHaveBeenCalledWith({
      provider: "spotify",
      q: "Velvet",
      country: "",
    });
  });
  it("shows an actionable error and retry", () => {
    const retry = vi.fn();
    render(<DataState loading={false} error="API unavailable" retry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalled();
  });
  it("prevents pagination beyond the last page", () => {
    render(<Pagination offset={0} total={6} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });
});
