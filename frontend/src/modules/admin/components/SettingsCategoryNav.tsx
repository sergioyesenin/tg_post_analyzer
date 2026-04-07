import type { SettingsCategoryViewModel } from '@modules/admin/mappers';
import type { SettingsCategoryKey } from '@modules/admin/settings-catalog';
import { useTranslation } from 'react-i18next';

type SettingsCategoryNavProps = {
  categories: SettingsCategoryViewModel[];
  selectedCategoryKey: SettingsCategoryKey;
  onSelect: (key: SettingsCategoryKey) => void;
};

export function SettingsCategoryNav({ categories, selectedCategoryKey, onSelect }: SettingsCategoryNavProps) {
  const { t } = useTranslation();

  return (
    <section className="detail-block settings-category-nav" aria-label={t('admin.settings.categoryNavAria')}>
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">{t('states.admin')}</span>
          <strong>{t('admin.settings.categoryNavTitle')}</strong>
        </div>
      </div>

      <div className="settings-category-nav__list" role="tablist" aria-orientation="vertical">
        {categories.map((category) => {
          const isSelected = category.key === selectedCategoryKey;

          return (
            <button
              key={category.key}
              id={`settings-tab-${category.key}`}
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-expanded={isSelected}
              aria-controls={`settings-panel-${category.key}`}
              tabIndex={isSelected ? 0 : -1}
              className={`settings-category-nav__button ${isSelected ? 'settings-category-nav__button--active' : ''}`.trim()}
              onClick={() => onSelect(category.key)}
            >
              <span className="settings-category-nav__button-top">
                <strong>{category.label}</strong>
                <span>{t('admin.settings.categoryCounter', { count: category.parameterCount })}</span>
              </span>
              <span className="settings-category-nav__button-copy">{category.description}</span>
              {category.badge ? <span className="settings-category-nav__badge">{category.badge}</span> : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
