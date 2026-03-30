import { useTranslation } from 'react-i18next';

type EventWorkspaceSelectionContextProps = {
  title: string | null;
};

export function EventWorkspaceSelectionContext({ title }: EventWorkspaceSelectionContextProps) {
  const { t } = useTranslation();
  const hasSelection = title !== null;

  return (
    <section className={`workspace-selection-context ${hasSelection ? 'workspace-selection-context--active' : ''}`.trim()}>
      <span className="state-card__eyebrow">
        {t('events.workspaceSelection.eyebrow', { defaultValue: 'Контекст анализа' })}
      </span>
      <strong>
        {title ?? t('events.workspaceSelection.emptyTitle', { defaultValue: 'Событие не выбрано' })}
      </strong>
      <p>
        {hasSelection
          ? t('events.workspaceSelection.activeDescription', {
              defaultValue: 'Таблица, граф и правая панель сейчас синхронизированы вокруг этого события.',
            })
          : t('events.workspaceSelection.emptyDescription', {
              defaultValue: 'Выберите событие в таблице, чтобы открыть единое рабочее пространство списка, графа и панели деталей.',
            })}
      </p>
    </section>
  );
}
