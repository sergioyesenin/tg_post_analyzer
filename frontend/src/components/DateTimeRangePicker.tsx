type Props = {
  fromLocal: string;
  toLocal: string;
  onChange: (next: { fromLocal: string; toLocal: string }) => void;
  onApply: () => void;
  error?: string | null;
};

export default function DateTimeRangePicker({
  fromLocal,
  toLocal,
  onChange,
  onApply,
  error,
}: Props) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col md:flex-row gap-3 md:items-end">
        <label className="flex flex-col gap-1">
          <span className="text-sm text-gray-600">С</span>
          <input
            className="border rounded-lg px-3 py-2 bg-white"
            type="datetime-local"
            value={fromLocal}
            onChange={(e) => onChange({ fromLocal: e.target.value, toLocal })}
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-sm text-gray-600">По</span>
          <input
            className="border rounded-lg px-3 py-2 bg-white"
            type="datetime-local"
            value={toLocal}
            onChange={(e) => onChange({ fromLocal, toLocal: e.target.value })}
          />
        </label>

        <button
          className="rounded-lg px-4 py-2 border bg-black text-white disabled:opacity-50"
          onClick={onApply}
          disabled={!fromLocal || !toLocal || Boolean(error)}
        >
          Применить
        </button>
      </div>

      {error ? <div className="text-sm text-red-600">{error}</div> : null}
      <div className="text-xs text-gray-500">
        Выбирай даты/время в локальном часовом поясе — отправим в API в UTC.
      </div>
    </div>
  );
}
