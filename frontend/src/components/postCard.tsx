import { useMemo, useState } from "react";
import ExpandablePanel from "./expandablePanel";
import { usePostComments, usePostFull, usePostReport } from "../api/postDetails";

type Tab = "none" | "full" | "comments" | "report";

type Props = {
  post: {
    id: number;
    channel_username: string;
    text_preview?: string | null;
    comments_count?: number | null;
    views?: number | null;
    score?: number | null;
  };
};

function Button({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-3 py-1.5 rounded-lg border text-sm transition",
        active ? "bg-black text-white" : "bg-white hover:bg-gray-100",
      ].join(" ")}
      type="button"
    >
      {children}
    </button>
  );
}

export default function PostCard({ post }: Props) {
  const [tab, setTab] = useState<Tab>("none");

  const showFull = tab === "full";
  const showComments = tab === "comments";
  const showReport = tab === "report";

  // грузим данные только когда вкладка реально открыта
  const fullQ = usePostFull(post.id, showFull);
  const commentsQ = usePostComments(post.id, showComments);
  const reportQ = usePostReport(post.id, showReport);

  const title = useMemo(() => {
    if (showFull) return "Полный текст поста";
    if (showComments) return "Комментарии";
    if (showReport) return "ИИ-анализ комментариев";
    return "";
  }, [showFull, showComments, showReport]);

  const toggle = (next: Tab) => setTab((cur) => (cur === next ? "none" : next));

  return (
    <div className="bg-white p-4 rounded-xl shadow-sm border">
      <div className="font-semibold">@{post.channel_username}</div>

      <div className="text-sm text-gray-700 mt-2">
        {post.text_preview ?? "—"}
      </div>

      <div className="flex flex-wrap gap-4 text-sm text-gray-500 mt-3">
        <span>💬 {post.comments_count ?? 0}</span>
        <span>👀 {post.views ?? 0}</span>
        <span>⚡ {post.score ?? 0}</span>
      </div>

      {/* кнопки действий */}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button active={showFull} onClick={() => toggle("full")}>
          Полный текст
        </Button>

        <Button active={showComments} onClick={() => toggle("comments")}>
          Комментарии
        </Button>

        <Button active={showReport} onClick={() => toggle("report")}>
          ИИ-анализ
        </Button>
      </div>

      {/* раскрывающаяся область */}
      {tab !== "none" && (
        <ExpandablePanel title={title}>
          {showFull && (
            <>
              {fullQ.isLoading ? <div>Загрузка…</div> : null}
              {fullQ.isError ? (
                <div className="text-red-600">Не удалось загрузить полный текст</div>
              ) : null}
              {fullQ.data ? (
                <pre className="whitespace-pre-wrap text-sm text-gray-800">
                  {fullQ.data.text ?? "—"}
                </pre>
              ) : null}
            </>
          )}

          {showComments && (
            <>
              {commentsQ.isLoading ? <div>Загрузка…</div> : null}
              {commentsQ.isError ? (
                <div className="text-red-600">Не удалось загрузить комментарии</div>
              ) : null}

              {commentsQ.data && commentsQ.data.length === 0 ? (
                <div className="text-sm text-gray-600">Комментариев нет</div>
              ) : null}

              <div className="space-y-3">
                {(commentsQ.data ?? []).map((c) => (
                  <div key={c.id} className="border rounded-lg p-3 bg-white">
                    {(c.author || c.date) && (
                      <div className="text-xs text-gray-500 mb-1">
                        {c.author ?? "unknown"}
                        {c.date ? ` · ${new Date(c.date).toLocaleString()}` : ""}
                      </div>
                    )}
                    <div className="text-sm text-gray-800 whitespace-pre-wrap">
                      {c.text ?? "—"}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {showReport && (
            <>
              {reportQ.isLoading ? <div>Загрузка…</div> : null}
              {reportQ.isError ? (
                <div className="text-red-600">Не удалось загрузить ИИ-анализ</div>
              ) : null}

              {reportQ.data?.content ? (
                <pre className="whitespace-pre-wrap text-sm text-gray-800">
                  {reportQ.data.content}
                </pre>
              ) : reportQ.isSuccess ? (
                <div className="text-sm text-gray-600">Анализа пока нет</div>
              ) : null}
            </>
          )}
        </ExpandablePanel>
      )}
    </div>
  );
}
