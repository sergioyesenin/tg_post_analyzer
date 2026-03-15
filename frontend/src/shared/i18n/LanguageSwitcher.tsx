import { useTranslation } from 'react-i18next';

const languages = ['ru', 'en'] as const;

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();

  return (
    <div className="app-language-switcher" aria-label={t('language.label')}>
      {languages.map((language) => (
        <button
          key={language}
          type="button"
          className="app-session-chip__action"
          disabled={i18n.resolvedLanguage === language}
          onClick={() => {
            void i18n.changeLanguage(language);
          }}
        >
          {t(`language.${language}`)}
        </button>
      ))}
    </div>
  );
}
