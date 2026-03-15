import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import enCommon from '@shared/i18n/locales/en/common.json';
import ruCommon from '@shared/i18n/locales/ru/common.json';

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { common: ruCommon },
      en: { common: enCommon },
    },
    lng: 'ru',
    fallbackLng: 'en',
    defaultNS: 'common',
    ns: ['common'],
    supportedLngs: ['ru', 'en'],
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['querystring', 'localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupQuerystring: 'lang',
    },
  });

export { i18n };
