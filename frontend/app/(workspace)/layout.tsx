import { Navigation } from "@/components/layout/navigation";
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-4"
      >
        Skip to content
      </a>
      <Navigation />
      <div className="lg:ml-60">
        <header className="flex items-center justify-between border-b border-border bg-white px-6 py-5">
          <span className="text-sm text-muted-foreground">
            Your music intelligence workspace
          </span>
          <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            Catalogue analytics
          </span>
        </header>
        <main id="main" className="mx-auto max-w-7xl p-6 lg:p-10">
          {children}
        </main>
        <footer className="px-6 py-8 text-xs text-muted-foreground">
          Metrics describe the tracked catalogue. Unavailable metrics are never
          estimated.
        </footer>
      </div>
    </>
  );
}
