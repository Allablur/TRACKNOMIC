import { ArtistDetail } from "@/components/dashboard/artist-detail";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ArtistDetail id={id} />;
}
