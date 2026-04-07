import { useTranslation } from 'react-i18next';

import type { SettingsCategoryViewModel } from '@modules/admin/mappers';

type SettingsCategoryDetailsProps = {
  category: SettingsCategoryViewModel;
};

export function SettingsCategoryDetails({ category }: SettingsCategoryDetailsProps) {
  const { t } = useTranslation();

  return (
    <section
      id={`settings-panel-${category.key}`}
      className="detail-block settings-category-panel"
      role="tabpanel"
      aria-labelledby={`settings-tab-${category.key}`}
    >
      <div className="detail-block__header settings-category-panel__header">
        <div>
          <span className="state-card__eyebrow">{t('states.edit')}</span>
          <strong>{category.label}</strong>
          <p className="dashboard-panel-copy">{category.description}</p>
        </div>
        <div className="settings-category-panel__meta">
          <span>{t('admin.settings.categoryCounter', { count: category.parameterCount })}</span>
          <span>{t('admin.settings.configuredCounter', { count: category.configuredCount })}</span>
        </div>
      </div>

      <div className="workspace-selection-context workspace-selection-context--active">
        <strong>{t('admin.settings.parameterListTitle')}</strong>
        <p>{t('admin.settings.parameterListDescription')}</p>
      </div>

      <div className="settings-parameter-list">
        {category.parameters.map((parameter) => (
          <article key={parameter.key} className="settings-parameter-card">
            <div className="settings-parameter-card__header">
              <div>
                <strong>{parameter.label}</strong>
                <span className="settings-parameter-card__key">{parameter.key}</span>
              </div>
              {!parameter.isDocumented ? <span className="settings-parameter-card__badge">{t('admin.settings.fallbackBadge')}</span> : null}
            </div>
            <p className="dashboard-panel-copy">{parameter.purpose}</p>
            <div className="settings-parameter-card__facts">
              <div>
                <span>{t('admin.settings.allowedValuesLabel')}</span>
                <strong>{parameter.allowedValues}</strong>
              </div>
              <div>
                <span>{t('admin.settings.effectiveValueLabel')}</span>
                <strong>{parameter.effectiveDisplayValue}</strong>
              </div>
              <div>
                <span>{t('admin.settings.editableValueLabel')}</span>
                <strong>{parameter.hasEditableValue ? parameter.editableDisplayValue : t('admin.settings.notSetLabel')}</strong>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
