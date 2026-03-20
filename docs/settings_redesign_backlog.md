# Settings Redesign Backlog

## Problem Interpretation

Идея решает три конкретные проблемы на `/settings`:

- Админ должен редактировать raw JSON в `textarea`, чтобы поменять один параметр
- Названия параметров и их смысл даны в английских технических ключах, что повышает риск ошибки и замедляет работу
- Экран не соответствует модели `найти нужную настройку -> понять, что она делает -> безопасно изменить -> сохранить`, которая используется в современных интерфейсах настроек

Целевой пользователь: `admin`, потому что только он может изменять настройки.

Сценарий: админ заходит в `/settings`, хочет изменить конкретный параметр проекта, например polling interval, rollout percentage или лимит, и должен сделать это без знания JSON-синтаксиса и без чтения backend-ключей.

Что видно из локального кода:

- текущий экран `frontend/src/modules/admin/routes/SettingsPage.tsx` позволяет администратору выбрать scope и редактировать `value_json_text` в `textarea`
- backend уже знает допустимые scopes и ограничения по полям через `services/settings_validation.py`
- settings разбиты на группы: `ingest`, `reports`, `retention`, `jobs`, `api`, `scheduler`, `monitor`, `features` в `services/settings_defaults.py`
- update API принимает `PUT /api/settings/{key}` и сохраняет объект по scope, а не отдельные поля, в `api/routers/settings.py`

Что подтверждается внешними паттернами современных продуктов:

- настройки организуются по разделам и категориям, а не как единый технический JSON-блок
- основная единица взаимодействия пользователя — поле формы с понятным label и helper text, а не технический ключ
- сохранение выполняется явно и предсказуемо, обычно на уровне секции или страницы

Вывод: production-ready решение здесь не в том, чтобы косметически улучшить JSON-редактор, а в том, чтобы заменить JSON-редактирование на structured settings UI с категориями, русскими label и description, типизированными контролами и валидацией на уровне поля.

## User Flow

1. Админ открывает `/settings`
2. Видит список категорий настроек в левом navigation или side panel:
   - `ingest`
   - `reports`
   - `retention`
   - `jobs`
   - `api`
   - `scheduler`
   - `monitor`
   - `features`
3. Выбирает категорию
4. Видит список параметров этой категории в виде формы:
   - label на русском
   - краткое описание на русском
   - тип поля
   - текущее значение
   - допустимый диапазон или формат
   - значение по умолчанию
5. Меняет одно или несколько полей
6. UI валидирует ввод до отправки
7. Пользователь нажимает `Сохранить`
8. Система отправляет обновленный payload для выбранного scope через `PUT /api/settings/{key}`
9. После успешного сохранения пользователь видит подтверждение, а effective settings обновляются

Точки взаимодействия:

- sidebar категорий
- поиск по настройкам
- поле формы
- reset или revert изменений
- save action
- блок `effective settings`
- optional advanced raw JSON view, если он сохраняется для диагностики

Возможные ошибки:

- backend `403`
- backend `422` на невалидное значение
- network или server error
- админ меняет значение и уходит со страницы без сохранения
- пользователь вводит число вне допустимого диапазона
- поле зависит от другого поля, например `scheduler.enabled = false`

## UI Behavior

Что видит пользователь:

- hero-блок с кратким описанием экрана
- sidebar категорий настроек
- строку поиска по названиям настроек
- главную панель с типизированной формой выбранной категории
- secondary panel с effective settings summary или read-only technical details
- для каждого поля:
  - русскоязычный label
  - краткое описание
  - helper text с диапазоном или единицей измерения
  - default value
  - текущий статус: `changed`, `saved`, `invalid`

Какие действия доступны:

- выбрать категорию
- найти настройку по русскому названию или техключу
- менять значения через контролы по типу:
  - boolean -> switch
  - integer или float -> numeric input
  - percent или rate -> numeric input с unit label
  - hour или minute -> numeric input с диапазоном
- сбросить поле к effective/current value
- сбросить поле к canonical default
- сохранить изменения по категории
- отменить несохраненные изменения
- просмотреть read-only technical key
- просмотреть effective settings payload

Обязательные UI states:

- `loading`: экран загружает effective settings и metadata формы
- `success`: форма загружена и доступна для редактирования
- `dirty`: есть несохраненные изменения
- `saving`: submit in progress, save disabled
- `saved`: показан success feedback после сохранения
- `field-error`: ошибка конкретного поля
- `section-error`: ошибка сохранения категории
- `forbidden`: пользователь не может редактировать настройки
- `empty-search`: поиск по настройкам не нашел полей
- `disabled`: поле или секция заблокированы условиями

Точное ожидаемое поведение:

- Пользователь не редактирует JSON для стандартного сценария изменения параметров
- Каждая настройка редактируется через контрол, соответствующий ее типу
- Технический ключ не является primary label; он показывается как secondary metadata
- Все поля валидируются на клиенте по тем же ограничениям, что и backend
- Сохранение работает на уровне категории или scope, потому что текущий backend API принимает payload по scope
- При наличии несохраненных изменений при смене категории или уходе со страницы показывается confirm dialog
- Аналитик на `/settings` сохраняет текущий read-only сценарий и не видит controls редактирования

## Task List

### 1. Define settings information architecture for `/settings`

- `title`: Replace JSON-first settings screen with category-based settings architecture
- `priority`: P0
- `area/screen`: `/settings`
- `problem`: Текущий экран организован вокруг raw JSON, а не вокруг задач администратора
- `expected behavior`: Экран настроек разбит на тематические категории, каждая категория открывает форму только для связанных параметров
- `acceptance criteria`:
  - На экране отображаются 8 категорий на основе backend scopes: `ingest`, `reports`, `retention`, `jobs`, `api`, `scheduler`, `monitor`, `features`
  - Категории отображаются в отдельной navigation area
  - При выборе категории в контентной области показываются только поля выбранного scope
  - По умолчанию открывается первая доступная категория или категория из URL
  - Текущая выбранная категория сохраняется в URL query param, например `?section=jobs`
- `UI states`:
  - `loading`
  - `success`
  - `forbidden`
  - `empty`
- `edge cases`:
  - неизвестная категория в URL
  - backend вернул пустой список editable settings
- `dependencies`:
  - current settings scopes from backend
- `estimate`: M

### 2. Add settings metadata layer for human-readable labels, descriptions, units, and control types

- `title`: Introduce frontend metadata registry for settings fields
- `priority`: P0
- `area/screen`: `/settings`
- `problem`: Backend keys вроде `ai_poll_seconds` и `keyword_graph_rollout_percent` непонятны администратору без технического контекста
- `expected behavior`: Каждое поле имеет локализованный label, description, unit, control type и hint, используемые для рендеринга формы
- `acceptance criteria`:
  - Для каждого поля из canonical settings defaults существует metadata entry
  - Metadata entry содержит:
    - technical key
    - human label RU
    - optional human label EN
    - description RU
    - input type
    - unit if applicable
    - sort order within section
  - Отсутствие metadata для поля приводит к явному fallback rendering, а не к silent omission
  - Technical key отображается в UI как secondary text, а не как primary label
- `UI states`:
  - `standard field rendering`
  - `fallback field rendering`
- `edge cases`:
  - новый backend key появился без metadata
  - deprecated key остался в effective payload
- `dependencies`:
  - canonical settings keys from backend
- `estimate`: M

### 3. Replace raw JSON editor with typed form controls

- `title`: Implement typed settings form per scope instead of JSON textarea
- `priority`: P0
- `area/screen`: `/settings`
- `problem`: JSON textarea делает изменение одной настройки медленным и рискованным
- `expected behavior`: Для выбранной категории пользователь редактирует параметры через типизированные поля, не видя JSON как основной способ редактирования
- `acceptance criteria`:
  - Boolean fields рендерятся как switch или checkbox
  - Integer and float fields рендерятся как numeric inputs
  - Percent-like fields отображают unit рядом с input
  - Для каждого поля показывается текущее effective value
  - Для каждого поля отображается default value
  - `textarea` с raw JSON не является primary editing control на основном экране
  - Save отправляет `PUT /api/settings/{scope}` с полным payload scope
- `UI states`:
  - `loading`
  - `success`
  - `dirty`
  - `saving`
  - `saved`
  - `field-error`
  - `section-error`
- `edge cases`:
  - пользователь очищает numeric field
  - float field вводится с локальной запятой
  - булевый toggle меняет доступность зависимых полей
- `dependencies`:
  - metadata registry
  - existing `PUT /api/settings/{key}`
- `estimate`: L

### 4. Mirror backend validation rules in client-side form validation

- `title`: Add field-level validation aligned with backend settings constraints
- `priority`: P0
- `area/screen`: `/settings`
- `problem`: Сейчас UI проверяет только `валидный JSON-объект`, а не смысловые ограничения отдельных полей
- `expected behavior`: Пользователь получает ошибку на уровне конкретного поля до отправки формы
- `acceptance criteria`:
  - Для всех полей в UI отражены min/max constraints из backend validation
  - Save blocked when at least one field is invalid
  - Error message показывается рядом с полем
  - Ошибка `422` от backend маппится в field-level или section-level error
  - Client validation и backend validation не расходятся по поддерживаемым диапазонам для известных полей
- `UI states`:
  - `valid`
  - `invalid`
  - `server-validation-error`
- `edge cases`:
  - min > max из-за частично введенных значений
  - значения типа `0`, `0.0`, `false`
  - hidden or disabled field still present in payload
- `dependencies`:
  - `services/settings_validation.py`
- `estimate`: M

### 5. Add search and filtering inside settings

- `title`: Add settings search by human label and technical key
- `priority`: P1
- `area/screen`: `/settings`
- `problem`: При росте числа параметров админу сложно находить нужную настройку внутри категорий
- `expected behavior`: Пользователь может найти настройку по русскому названию, английскому technical key или description
- `acceptance criteria`:
  - На экране есть search input
  - Search фильтрует список полей в реальном времени
  - Search работает по:
    - human label
    - technical key
    - description
  - При отсутствии совпадений показывается dedicated empty state
  - Search не меняет сохраненные значения и не вызывает API
- `UI states`:
  - `default`
  - `filtered`
  - `empty-search`
- `edge cases`:
  - search query совпадает только с technical key
  - active search скрывает currently invalid field
- `dependencies`:
  - metadata registry
- `estimate`: S

### 6. Add unsaved-changes protection and scoped save behavior

- `title`: Prevent silent loss of settings edits
- `priority`: P0
- `area/screen`: `/settings`
- `problem`: При category switch, route change или reload админ может потерять изменения без предупреждения
- `expected behavior`: При наличии несохраненных изменений пользователь получает явное предупреждение
- `acceptance criteria`:
  - При изменении хотя бы одного поля форма получает dirty state
  - При смене категории с dirty state показывается confirm dialog
  - При уходе со страницы или route change с dirty state показывается confirm dialog
  - После успешного сохранения dirty state сбрасывается
  - Save относится только к выбранной категории, не ко всем settings сразу
- `UI states`:
  - `clean`
  - `dirty`
  - `confirm-leave`
  - `saved`
- `edge cases`:
  - пользователь нажал browser back
  - сохранение прошло успешно, но effective settings refetch еще не завершен
- `dependencies`:
  - typed form state
- `estimate`: M

### 7. Preserve analyst read-only mode and redesign its presentation

- `title`: Keep analyst settings access read-only with structured presentation
- `priority`: P1
- `area/screen`: `/settings`
- `problem`: У аналитика есть доступ к effective settings, но current UI показывает technical payload, а не понятную read-only структуру
- `expected behavior`: Аналитик видит те же категории и поля, но без возможности редактирования
- `acceptance criteria`:
  - Для `analyst` не отображаются save controls
  - Для `analyst` поля рендерятся в read-only mode
  - Аналитик может переключать категории и просматривать effective values
  - Raw effective JSON может быть доступен как secondary technical panel, но не как основной контент
- `UI states`:
  - `loading`
  - `read-only`
  - `forbidden`
  - `error`
- `edge cases`:
  - backend вернул `403` на `/api/settings/effective`
- `dependencies`:
  - existing RBAC
- `estimate`: M

### 8. Add optional advanced raw JSON fallback for admin diagnostics

- `title`: Keep raw JSON view as secondary advanced tool, not primary editing path
- `priority`: P2
- `area/screen`: `/settings`
- `problem`: Иногда администратору или разработчику может понадобиться inspect/debug payload, но это не должен быть основной UX
- `expected behavior`: Raw JSON доступен только как advanced disclosure block
- `acceptance criteria`:
  - Основной edit flow не использует JSON textarea
  - Raw JSON hidden by default
  - Raw JSON доступен через explicit `Technical details` или `Show raw payload`
  - В advanced block нет primary CTA, который конкурирует с structured form
- `UI states`:
  - `collapsed`
  - `expanded`
- `edge cases`:
  - payload содержит поле без metadata
- `dependencies`:
  - structured settings form
- `estimate`: S

### 9. Add automated coverage for settings form behavior

- `title`: Add screen-level tests for structured settings editing
- `priority`: P0
- `area/screen`: frontend test suite
- `problem`: Без тестов легко сломать RBAC, validation, dirty-state protection и payload mapping
- `expected behavior`: Новый settings flow покрыт тестами на route/screen level
- `acceptance criteria`:
  - Есть тест на render category navigation
  - Есть тест на field rendering by type
  - Есть тест на client-side validation
  - Есть тест на save payload for one scope
  - Есть тест на unsaved changes confirm
  - Есть тест на analyst read-only mode
  - Есть тест на search or filter
- `UI states`:
  - `loading`
  - `success`
  - `dirty`
  - `validation-error`
  - `saved`
  - `read-only`
  - `forbidden`
- `edge cases`:
  - unknown field metadata fallback
  - invalid URL section
- `dependencies`:
  - new settings UI implementation
- `estimate`: M

## Assumptions

- Основной редактируемый пользователь только `admin`; `analyst` остается read-only
- Scope `ingest`, `reports`, `retention`, `jobs`, `api`, `scheduler`, `monitor`, `features` останутся основными категориями экрана
- Текущий backend API `PUT /api/settings/{key}` сохраняется, и frontend будет собирать полный payload категории перед submit
- Для frontend допустимо завести metadata registry вручную, если backend пока не отдает labels, descriptions и control types
- Русский язык должен быть primary UI language для labels и descriptions на этом экране
- Raw JSON можно оставить только как secondary diagnostics mode
- Рекомендованный паттерн для целевого экрана: sidebar categories + scoped forms + per-field controls + search + explicit save

## Risks

- Главный риск: backend не отдает metadata для полей, поэтому frontend придется поддерживать ручной словарь labels, descriptions и control types
- Риск расхождения валидации: если ограничения в backend изменятся, frontend validation может устареть
- Риск масштаба: `убрать JSON` на практике означает не одну задачу, а redesign информации, metadata layer, form renderer, validation и tests
- Риск локализации: русские labels и descriptions нужно один раз хорошо нормализовать, иначе UI станет понятнее технически, но останется неоднородным
- Риск hidden complexity: некоторые поля могут требовать зависимого поведения, например disabled states или conditional hints
- Риск payload integrity: поскольку backend принимает scope-object целиком, frontend обязан корректно собирать полный payload и не терять неизмененные поля
