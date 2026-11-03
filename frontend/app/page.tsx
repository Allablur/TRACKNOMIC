import Link from "next/link";
import { AudioLines, ArrowUpRight, Database, Layers3 } from "lucide-react";
import { Button } from "@/components/ui/button";
export default function Home() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <Link
            href="/"
            className="flex items-center gap-3 text-xl font-semibold tracking-tight"
          >
            <AudioLines aria-hidden="true" className="text-primary" />
            Trackonomics
          </Link>
          <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium">
            Music catalogue intelligence
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
        <p className="mb-5 text-xs font-semibold tracking-[0.2em] text-primary uppercase">
          A clearer view of music
        </p>
        <h1 className="max-w-3xl text-5xl leading-tight font-semibold tracking-tight sm:text-7xl">
          Every catalogue
          <br />
          has a story.
        </h1>
        <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground">
          Explore attributed artist metadata, compare catalogues, and uncover
          patterns in release activity. Turn the music you track into clear,
          exportable insights.
        </p>
        <div className="mt-9">
          <Button asChild>
            <Link href="/dashboard">
              Open dashboard
              <ArrowUpRight aria-hidden="true" size={16} />
            </Link>
          </Button>
        </div>
        <section
          id="features"
          aria-label="Catalogue features"
          className="mt-24 grid gap-6 border-t border-border pt-8 sm:grid-cols-3"
        >
          {[
            {
              icon: AudioLines,
              title: "Artist intelligence",
              text: "Explore attributed artist metadata and tracked discographies.",
            },
            {
              icon: Layers3,
              title: "Catalogue insights",
              text: "Compare release activity and genre representation in your catalogue.",
            },
            {
              icon: Database,
              title: "Data with provenance",
              text: "MusicBrainz first. Missing metrics will stay unavailable.",
            },
          ].map(({ icon: Icon, title, text }) => (
            <article key={title}>
              <Icon
                aria-hidden="true"
                className="mb-5 text-primary"
                size={22}
              />
              <h2 className="font-semibold">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {text}
              </p>
            </article>
          ))}
        </section>
      </main>
      <footer className="mx-auto max-w-6xl border-t border-border px-6 py-6 text-xs text-muted-foreground">
        Trackonomics · Music industry analytics · Source attribution on every
        record
      </footer>
    </div>
  );
}
