import { useMemo, useState } from "react";
import DateTimeRangePicker from "./components/DateTimeRangePicker";
import { useChannels, useTopPosts } from "./api/hooks";
import PostCard from "./components/postCard";

// local datetime-local ("YYYY-MM-DDTHH:mm") -> ISO UTC string
function localDateTimeToIsoUtc(local: string): string {
  // new Date("YYYY-MM-DDTHH:mm") интерпретирует как local time
  const d = new Date(local);
  return d.toISOString();
}

function nowLocalInputValue(): string {
  const d = new Date();
  // datetime-local требует формат без секунд: YYYY-MM-DDTHH:mm
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function hoursAgoLocalInputValue(hours: number): string {
  const d = new Date(Date.now() - hours * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

export default function App() {
  // Черновик диапазона (поля ввода)
  const [draftFrom, setDraftFrom] = useState<string>(hoursAgoLocalInputValue(24));
  const [draftTo, setDraftTo] = useState<string>(nowLocalInputValue());

  // Примененный диапазон (именно он идет в запрос)
  const [applied, setApplied] = useState<{ fromLocal: string; toLocal: string }>({
    fromLocal: draftFrom,
    toLocal: draftTo,
  });

  const error = useMemo(() => {
    if (!draftFrom || !draftTo) return null;
    const a = new Date(draftFrom).getTime();
    const b = new Date(draftTo).getTime();
    if (Number.isNaN(a) || Number.isNaN(b)) return "Некорректная дата";
    if (a >= b) return "Дата «С» должна быть меньше даты «По»";
    return null;
  }, [draftFrom, draftTo]);

  const fromIsoUtc = useMemo(() => localDateTimeToIsoUtc(applied.fromLocal), [applied.fromLocal]);
  const toIsoUtc = useMemo(() => localDateTimeToIsoUtc(applied.toLocal), [applied.toLocal]);

  const channelsQ = useChannels();
  const topPostsQ = useTopPosts({ fromIsoUtc, toIsoUtc });

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <header className="space-y-3">
          <h1 className="text-3xl font-bold">Telegram Post Analyzer</h1>

          <DateTimeRangePicker
            fromLocal={draftFrom}
            toLocal={draftTo}
            error={error}
            onChange={({ fromLocal, toLocal }) => {
              setDraftFrom(fromLocal);
              setDraftTo(toLocal);
            }}
            onApply={() => {
              if (!error && draftFrom && draftTo) {
                setApplied({ fromLocal: draftFrom, toLocal: draftTo });
              }
            }}
          />
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Channels */}
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Отслеживаемые каналы</h2>
            {channelsQ.isLoading ? <div>Загрузка…</div> : null}
            {channelsQ.isError ? <div className="text-red-600">Ошибка загрузки каналов</div> : null}
            <div className="space-y-4">
              {(channelsQ.data ?? []).map((channel: any) => (
                <div key={channel.id} className="bg-white p-4 rounded-xl shadow-sm border">
                  <div className="font-semibold">@{channel.username}</div>
                  <div className="text-sm text-gray-500">
                    {channel.title} • {channel.category}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Top Posts */}
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xl font-semibold">Наиболее комментируемые посты</h2>
              {topPostsQ.isFetching ? (
                <span className="text-sm text-gray-500">обновление…</span>
              ) : null}
            </div>

            {topPostsQ.isLoading ? <div>Загрузка…</div> : null}
            {topPostsQ.isError ? (
              <div className="text-red-600">
                Ошибка загрузки топ-постов
              </div>
            ) : null}

            <div className="space-y-4">
              {(topPostsQ.data ?? []).map((post: any) => (
                <PostCard
                  key={post.id}
                  post={{
                    id: post.id,
                    channel_username: post.channel_username,
                    text_preview: post.text_preview,
                    comments_count: post.comments_count,
                    views: post.views,
                    score: post.score,
                  }}
                />
              ))}

              {topPostsQ.data && topPostsQ.data.length === 0 ? (
                <div className="text-gray-500">Нет постов за выбранный период</div>
              ) : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
