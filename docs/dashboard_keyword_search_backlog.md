# Dashboard Keyword Search Backlog

## Problem Interpretation

Идея решает конкретную проблему навигации внутри аналитического контура: пользователь видит агрегированные списки на `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes`, но не может быстро сузить выборку по свободному текстовому запросу и найти сущность по теме или ключевым словам.

Основной пользователь для этой функции: `analyst`. Вторичный пользователь: `admin`. Для `viewer` идея в текущем виде конфликтует с backend-контрактом: `/search/posts` в `api/routers/keyword_graph.py` доступен только ролям `admin` и `analyst`, а dashboard-маршруты доступны также `viewer`.

Сценарии использования:

- На `/dashboard/posts` пользователь знает тему или фразу и хочет быстро найти релевантные посты.
- На `/dashboard/events` пользователь хочет найти событие через связанные посты, содержащие нужные ключевые слова.
- На `/dashboard/processes` пользователь хочет найти процесс через события и посты, в которых встречается нужная тема.

Важно: endpoint `/search/posts` возвращает только посты, а не события и не процессы. Значит для `events` и `processes` поиск должен быть построен как поиск по связанным постам с последующим маппингом результатов к событиям и процессам, либо scope должен быть ограничен только `/dashboard/posts`.

## User Flow

1. Пользователь открывает один из маршрутов:
   - `/dashboard/posts`
   - `/dashboard/events`
   - `/dashboard/processes`
2. В верхней части экрана, рядом с текущими dashboard filters, пользователь видит строку поиска по ключевым словам.
3. Пользователь вводит запрос длиной от 2 до 200 символов.
4. Пользователь запускает поиск:
   - нажимает `Enter` в поле
   - или нажимает кнопку `Найти`
5. Система отправляет запрос в `/api/keyword/search/posts` с учетом:
   - `query`
   - `limit`
   - `date_from/date_to` из текущего dashboard filter state, если они заданы
   - `channel_ids` из текущего dashboard filter state, если этот фильтр есть у режима
6. Система обрабатывает результат по-разному в зависимости от экрана:
   - `posts`: показывает только посты, вернувшиеся из поиска
   - `events`: показывает только события, у которых есть пересечение `post_ids` с найденными постами
   - `processes`: показывает только процессы, у которых есть пересечение `event_ids` -> `post_ids` с найденными постами
7. Пользователь может:
   - очистить поисковый запрос
   - изменить запрос и повторить поиск
   - перейти в детальный экран сущности из таблицы результатов
   - комбинировать keyword search с обычными dashboard filters
8. При ошибке пользователь видит inline error state и может повторить попытку.

Точки взаимодействия:

- input поиска
- кнопка submit
- кнопка clear/reset search
- таблица результатов
- URL query params
- существующий filter bar

Возможные ошибки:

- запрос короче 2 символов
- backend вернул `403`
- backend вернул `404` из-за feature flag или rollout gate
- backend вернул `500`
- backend вернул `200`, но `items = []`
- на `events/processes` посты найдены, но после маппинга нет ни одного события или процесса

## UI Behavior

Что видит пользователь:

- На каждом dashboard отдельный блок `Keyword search` над таблицей данных
- Поле ввода с placeholder `Введите ключевое слово или фразу`
- Кнопка `Найти`
- Кнопка `Сбросить поиск`
- Текущий поисковый запрос отражен в URL, чтобы состояние было shareable и восстанавливалось после reload

Какие действия доступны:

- Ввести строку поиска
- Запустить поиск
- Очистить поиск
- Изменить обычные фильтры и повторно выполнить поиск
- Перейти в детальную карточку строки результата

Обязательные состояния:

- `default`: поле пустое, поиск не активен, таблица показывает обычный dashboard dataset
- `loading`: после submit кнопка disabled, показывается inline loading state над таблицей или в таблице
- `success`: таблица отфильтрована по результатам keyword search
- `empty-search`: backend вернул 0 постов
- `empty-mapped`: посты найдены, но ни одно событие или процесс не сматчено
- `error-403`: поиск недоступен по роли
- `error-404`: поиск недоступен из-за feature flag или rollout
- `error-generic`: общая ошибка API
- `disabled`: submit disabled, если `query.trim().length < 2` или идет запрос

Точное ожидаемое поведение:

- Поиск запускается только по explicit submit, не на каждый keypress
- Поиск не ломает текущие dashboard filters, а работает поверх них
- При `reset search` keyword query удаляется из URL, и экран возвращается к обычной dashboard-выборке
- На `posts` таблица строится только по `post_id`, пришедшим из поиска
- На `events` таблица строится только по событиям, где `item.post_ids` пересекаются с найденными `post_id`
- На `processes` таблица строится только по процессам, где хотя бы один `event_id` процесса связан с найденными постами через доступный graph или mapping data
- Если надежного источника связи `process -> event -> post` нет, задача не уходит в разработку как одна frontend-задача без backend dependency

## Task List

### 1. Add keyword search UX and URL state for dashboard screens

- `title`: Add explicit keyword search control to posts/events/processes dashboards
- `priority`: P0
- `area/screen`: `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes`
- `problem`: Пользователь не может сузить dashboard-данные по свободному текстовому запросу и быстро найти сущность по теме.
- `expected behavior`: На каждом dashboard есть единый search block с input, submit и reset; состояние поиска хранится в URL и восстанавливается после reload/back-forward navigation.
- `acceptance criteria`:
  - На каждом из трех маршрутов отображается input поиска и кнопки `Найти` и `Сбросить поиск`
  - При вводе менее 2 символов кнопка `Найти` disabled
  - После submit query сохраняется в URL как отдельный query param
  - После reload страницы query восстанавливается из URL в поле ввода
  - Нажатие `Сбросить поиск` удаляет query param из URL и возвращает экран в обычное dashboard-состояние
  - Поиск не запускается автоматически при вводе текста без submit
- `UI states`:
  - `default`
  - `disabled`
  - `dirty form`
  - `loading`
- `edge cases`:
  - query состоит только из пробелов
  - query длиннее 200 символов
  - пользователь меняет dashboard mode через mode switcher
- `dependencies`:
  - расширение dashboard filter parsing/serialization для нового `query` param
- `estimate`: M

### 2. Integrate posts dashboard with `/api/keyword/search/posts`

- `title`: Filter posts dashboard dataset by keyword search results
- `priority`: P0
- `area/screen`: `/dashboard/posts`
- `problem`: Даже при наличии search UI posts dashboard не умеет применить результат `/search/posts` к своей таблице.
- `expected behavior`: После успешного keyword search posts dashboard показывает только посты, чьи `post_id` вернулись из `/api/keyword/search/posts`.
- `acceptance criteria`:
  - При submit с `query >= 2` frontend вызывает `/api/keyword/search/posts`
  - В payload передаются:
    - `query`
    - `limit` = текущее dashboard `limit` или отдельно зафиксированное значение, если команда выберет его как продуктовый стандарт
    - `date_from/date_to` из dashboard filters
    - `channel_ids` из dashboard filters
  - Если поиск вернул `N` post ids, таблица posts dashboard отображает только строки с этими `post_id`
  - Если найденные `post_id` не пересекаются с текущим dashboard dataset, таблица показывает empty state `По текущему запросу посты не найдены в этой выборке`
  - Summary cards остаются от dashboard snapshot и не пересчитываются на клиенте
- `UI states`:
  - `loading`
  - `success`
  - `empty-search`
  - `error-403`
  - `error-404`
  - `error-generic`
- `edge cases`:
  - dashboard snapshot загружен, но search response пустой
  - search response содержит post ids, которых нет в текущем dashboard limit
  - повторный submit того же запроса
- `dependencies`:
  - endpoint `/api/keyword/search/posts`
  - frontend query hook for keyword search
- `estimate`: M

### 3. Map keyword search results to events dashboard rows

- `title`: Filter events dashboard by posts matched through keyword search
- `priority`: P0
- `area/screen`: `/dashboard/events`
- `problem`: Пользователь мыслит темой или фразой, но на events dashboard нет способа найти события через связанные посты.
- `expected behavior`: После keyword search events dashboard показывает только события, у которых `post_ids` пересекаются с найденными постами.
- `acceptance criteria`:
  - После успешного вызова `/api/keyword/search/posts` frontend собирает set найденных `post_id`
  - В events table остаются только строки, где `item.post_ids` содержит хотя бы один найденный `post_id`
  - Если пересечений нет, экран показывает empty state с текстом, отличающимся от `поиск не дал постов`
  - Если query очищен, events dashboard возвращается к полной выборке текущего snapshot
  - Выбор события и правая панель работают только для отфильтрованных строк
- `UI states`:
  - `loading`
  - `success`
  - `empty-search`
  - `empty-mapped`
  - `error-403`
  - `error-404`
  - `error-generic`
- `edge cases`:
  - найденные посты относятся к каналам вне текущего events snapshot
  - выбранное событие исчезло после нового поиска
- `dependencies`:
  - наличие `post_ids` в `EventsDashboardItemDto`
- `estimate`: M

### 4. Validate feasibility of processes dashboard keyword search mapping

- `title`: Define data contract for mapping keyword-matched posts to processes
- `priority`: P0
- `area/screen`: `/dashboard/processes`
- `problem`: `/search/posts` возвращает посты, а текущий `ProcessesDashboardResponse` не содержит явной связи `process -> post_ids`, поэтому frontend не может надежно отфильтровать процессы только на основе текущего контракта.
- `expected behavior`: Перед реализацией UI-команда фиксирует единственный детерминированный способ маппинга search result в process rows.
- `acceptance criteria`:
  - Задокументирован один источник данных для связи найденных `post_id` с `process_id`
  - Если используется существующий API, в задаче указан конкретный контракт и поле
  - Если существующего контракта недостаточно, создана отдельная backend/API задача на добавление связи
  - До появления контракта frontend implementation for `/dashboard/processes` не стартует
- `UI states`:
  - `not applicable` до подтверждения контракта
- `edge cases`:
  - процесс содержит события без доступных `post_ids`
  - process snapshot загружен, но mapping требует отдельного graph API
- `dependencies`:
  - backend/API contract for process-to-post mapping
- `estimate`: S

### 5. Implement processes dashboard keyword filtering after contract confirmation

- `title`: Filter processes dashboard by keyword search using approved post-to-process mapping
- `priority`: P1
- `area/screen`: `/dashboard/processes`
- `problem`: После подтверждения контракта процессный dashboard должен поддерживать тот же поисковый паттерн, что и posts/events.
- `expected behavior`: После keyword search dashboard показывает только процессы, связанные с найденными постами по утвержденному mapping rule.
- `acceptance criteria`:
  - Используется только заранее утвержденный mapping contract
  - После submit отображаются только процессы, удовлетворяющие mapping rule
  - Если посты найдены, но процессы не сматчены, показывается `empty-mapped` state
  - Поведение reset и URL state совпадает с posts/events
- `UI states`:
  - `loading`
  - `success`
  - `empty-search`
  - `empty-mapped`
  - `error-403`
  - `error-404`
  - `error-generic`
- `edge cases`:
  - после нового поиска выбранный процесс больше не входит в выборку
- `dependencies`:
  - результат задачи 4
- `estimate`: M

### 6. Handle RBAC and feature-flag mismatch for dashboard search

- `title`: Define and implement dashboard search availability rules by role and backend rollout state
- `priority`: P0
- `area/screen`: все 3 dashboard-экрана
- `problem`: Dashboard доступен `viewer`, но `/search/posts` недоступен `viewer`; также endpoint может вернуть `404` из-за feature flag или rollout.
- `expected behavior`: Доступность search control детерминирована и одинакова на всех dashboards.
- `acceptance criteria`:
  - Для `admin` и `analyst` search control отображается
  - Для `viewer` выполнено одно из двух, и это явно зафиксировано в продуктовой постановке:
    - либо control скрыт полностью
    - либо control виден disabled с текстом причины
  - При `404` от backend пользователь видит сообщение `поиск недоступен для этой учетной записи или окружения`
  - При `403` пользователь видит сообщение `поиск недоступен для вашей роли`
- `UI states`:
  - `hidden`
  - `disabled-with-reason`
  - `unavailable`
  - `forbidden`
- `edge cases`:
  - пользователь открывает URL с `query`, но не имеет права на поиск
  - feature flag выключен после того, как query уже был в URL
- `dependencies`:
  - решение product/PM по поведению для `viewer`
- `estimate`: S

### 7. Add test coverage for dashboard keyword search

- `title`: Add automated coverage for keyword search behavior on dashboard screens
- `priority`: P0
- `area/screen`: test suite
- `problem`: Без тестов легко сломать URL state, RBAC, mapping logic и error states.
- `expected behavior`: Поведение поиска покрыто интеграционными тестами на уровне screen/routes.
- `acceptance criteria`:
  - Есть тест на submit search и вызов `/api/keyword/search/posts` на `/dashboard/posts`
  - Есть тест на client-side filtering rows на `/dashboard/posts`
  - Есть тест на mapping в `/dashboard/events`
  - Есть тест на `viewer` behavior
  - Есть тест на `404` unavailable state
  - Есть тест на `reset search`
  - Есть тест на восстановление search state из URL
- `UI states`:
  - `success`
  - `loading`
  - `empty-search`
  - `empty-mapped`
  - `error`
  - `disabled`
- `edge cases`:
  - query из пробелов
  - query < 2
  - повторный переход browser back/forward
- `dependencies`:
  - реализованные search hooks/components
- `estimate`: M

## Assumptions

- Поиск должен быть explicit-submit, а не live search
- Поиск должен работать поверх уже выбранных dashboard filters, а не заменять их
- На `/dashboard/posts` search results не заменяют backend dashboard API, а дополнительно фильтруют уже загруженный dataset на клиенте
- Summary cards и `generated_at` не пересчитываются на клиенте после поиска
- Для `events` допустимо фильтровать строки по пересечению `event.post_ids` с найденными `post_id`
- Для `viewer` search либо скрывается, либо disabled; в текущем backend-контракте полноценный доступ невозможен
- Для `/dashboard/processes` текущего контракта недостаточно для production-ready постановки без отдельного подтверждения mapping source

## Risks

- Главный риск: исходная идея звучит как единая задача, но по факту это минимум 3 задачи, и одна из них сейчас заблокирована контрактом данных
- RBAC-риск: `viewer` видит dashboard, но не может использовать `/search/posts`
- Product-риск: если фильтровать только текущий dashboard snapshot, пользователь может ожидать глобальный поиск, а получить поиск только внутри текущей выборки или лимита
- Data-contract риск: для `/dashboard/processes` нет явной связи от process к найденным `post_id` в текущем dashboard response
- UX-риск: если не различать `empty-search` и `empty-mapped`, пользователь не поймет, поиск ничего не нашел или маппинг к сущности не дал результата
- Tech-риск: при смене query нужно сбрасывать selection state на events/processes, иначе правая панель может ссылаться на уже скрытую строку
