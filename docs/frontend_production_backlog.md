# Frontend Production Backlog

Единый production-ready backlog для текущего фронтенда `tg_post_analyzer`.

Источник консолидации:

- аудит текущего интерфейса
- `docs/dashboard_keyword_search_backlog.md`
- `docs/settings_redesign_backlog.md`

Принципы сборки этого файла:

- задачи атомарны и проверяемы
- сохранен внутренний порядок задач из keyword search backlog
- сохранен внутренний порядок задач из settings redesign backlog
- пересекающиеся задачи не дублируются, а встроены в общую очередь через зависимости
- если задача из старого backlog конфликтовала с более детальной задачей из исходных docs, приоритет отдавался более детальной постановке

## Priority Model

- `P0` — блокирует продуктовый сценарий или системно ломает качество интерфейса
- `P1` — сильно ухудшает опыт, но не блокирует базовое использование
- `P2` — шероховатости, консистентность, операционное качество
- `P3` — polish

## Task Types

- `UI foundation`
- `UX flow fixes`
- `component refactor`
- `bugfix`
- `polish`

## Unified Backlog

| ID | Title | Priority | Type | Area / Screen | Problem | Expected behavior | Acceptance criteria | Dependencies | Complexity |
|---|---|---|---|---|---|---|---|---|---|
| UIF-001 | Ужать верхнюю shell-обвязку аналитических экранов | P0 | UI foundation | `AppShell`, `/dashboard/*`, `/reports/*`, `/keyword-graph` | Hero, session-card и верхние отступы съедают первый экран и уводят таблицы и графы ниже fold; session block в header собран вертикальной колонкой, занимает слишком много высоты и перетягивает внимание с рабочего контента | Пользователь видит ключевые данные или рабочую область без лишнего скролла; session block становится компактным служебным элементом, а не доминирующей карточкой | 1. На desktop 1440px таблица или summary+table начинает отображаться в первом экране на `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes`. 2. Высота header/shell визуально меньше текущей минимум на один крупный блок. 3. Session block не доминирует над контентом страницы. 4. Session block в `AppShell` отображается в 2 строки, а не в вертикальный стек. 5. Email пользователя не отображается в этой области. 6. Кнопка logout остается доступной и визуально встроенной в компактный layout. | — | M |
| UIF-002 | Ввести единый `page-meta` pattern вместо сырого правого текста | P1 | UI foundation | `/reports/*`, `/monitor`, `/jobs`, `/keyword-graph` | Метаданные справа выглядят как случайный текст, без визуального контейнера и иерархии | Все route-level метаданные оформлены единообразно и читаются как вторичный контекст | 1. Все блоки route meta используют один reusable component/style. 2. Meta не разваливается в hero. 3. У meta есть выравнивание, ограничение ширины и единая типографика. | UIF-001 | S |
| UIF-003 | Развести surface hierarchy для analytics, admin и ops | P1 | UI foundation | глобально, `global.css` | Один card-style натянут на все типы экранов, из-за чего нет визуальной иерархии | Аналитика, CRUD и operational UI визуально различаются по плотности и приоритетам | 1. Есть отдельные токены или классы для workspace, form-panel и ops-panel. 2. Admin и monitor/jobs визуально не выглядят как те же dashboard-card. 3. Вторичные блоки заметно менее акцентны, чем primary content. | UIF-001 | L |
| UIF-004 | Нормализовать hierarchy кнопок и destructive actions | P1 | UI foundation | admin, reports, jobs, detail pages | CTA, secondary и destructive действия выглядят несистемно | Действия читаются по приоритету: primary, secondary, tertiary, destructive | 1. Primary action на каждом экране одна и визуально самая сильная. 2. Destructive actions имеют отдельный стиль. 3. Повторяющиеся action patterns используют единые классы или компоненты. | UIF-003 | M |
| UIF-005 | Поднять контраст текста, статусов и muted-элементов | P1 | UI foundation | глобально, badges, meta, table secondary text | Светлые тексты и чипы плохо читаются на молочном фоне | Вторичный текст и статусы читаются без напряжения | 1. Secondary text читаем на всех основных карточках. 2. Badge warning, success и danger различимы не только цветом фона. 3. Нет ключевых KPI или статусов, которые визуально проваливаются. | UIF-003 | S |
| CRF-001 | Разделить `DashboardTableShell` на analytics, admin и ops table components | P0 | component refactor | shared tables, admin, jobs, monitor, dashboard | Один table-shell обслуживает слишком разные сценарии | Каждый домен использует таблицу, соответствующую своему сценарию | 1. Есть отдельные компоненты минимум для analytics table и admin or ops table. 2. Admin больше не импортирует dashboard-shell напрямую. 3. Табличные возможности можно развивать независимо по доменам. | — | L |
| CRF-002 | Убрать расхождение test/prod rendering у таблиц | P0 | component refactor | shared tables | В test рендерится одна таблица, в production другая | Тесты проверяют тот же UI-контракт, что видит пользователь | 1. Нет отдельного test-only DOM для таблицы. 2. Поведенческие тесты проходят на production-equivalent rendering. 3. Selection, action и cell rendering тестируются на реальном компоненте. | CRF-001 | M |
| CRF-003 | Вернуть таблицам count и управление длинной выборкой | P1 | component refactor | dashboard, reports, admin, jobs | Таблицы выглядят обрубленными: нет диапазона, count и контроля длины списка | Пользователь понимает размер списка и управляет навигацией по нему | 1. На каждой таблице виден count или range. 2. Для длинных списков есть pagination или явная стратегия limit. 3. Пользователь не теряет контекст длины выборки. | CRF-001 | M |
| CRF-004 | Восстановить сортировку там, где она продуктово нужна | P1 | component refactor | dashboard tables, reports tables, jobs tables | Таблицы отключили сортировку, хотя это ключевой аналитический инструмент | Пользователь может пересортировать данные по релевантным колонкам | 1. На dashboard доступны сортировки по подтвержденным колонкам. 2. В reports и jobs доступны сортировки по статусу, дате и размеру очереди там, где это поддержано контрактом. 3. Активная сортировка визуально читается. | CRF-001 | M |
| CRF-005 | Вынести page-layout primitives для hero, content, rail и meta | P2 | component refactor | route modules | Каждый route вручную собирает близкий, но разный layout | Страницы собираются из общих layout-блоков без дрейфа | 1. Hero, content, meta и secondary rail используют reusable layout primitives. 2. Новая страница не требует ручного CSS-сшивания. 3. Повторяющийся JSX в route files уменьшен. | UIF-001, UIF-002 | M |
| UXF-001 | Перевести dashboard filters с raw-input модели на product controls | P0 | UX flow fixes | `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes` | CSV и ручной ввод `channel_ids`, `categories`, `status`, `report_status` выглядит как API-форма | Фильтры подбираются через понятные контролы: selects, multi-select, chips, date pickers | 1. Пользователь может выбрать канал и статус без ручного ввода ID. 2. Ошибочный формат не может попасть в URL через UI. 3. Apply и Reset работают только с поддерживаемыми фильтрами. 4. URL остается source of truth. | данные для опций фильтров | L |
| UXF-002 | Добавить inline validation и понятные empty/error подсказки в dashboard filters | P1 | UX flow fixes | `/dashboard/*` | Форма фильтров не помогает понять допустимые значения и причины пустой выдачи | Пользователь понимает, почему фильтр не дал результата или не может быть применен | 1. Некорректные значения показывают inline validation. 2. Пустая выдача различает нет данных и слишком узкий фильтр. 3. Reset очищает именно фильтры режима. | UXF-001 | M |
| UXF-003 | Сделать selection-driven workspace явным для событий | P1 | UX flow fixes | `/dashboard/events` | Таблица, граф и detail rail слабо связаны визуально | Выбранное событие явно фиксируется как текущий контекст анализа | 1. Выбранная строка визуально заметна. 2. В graph/detail есть header с названием выбранного события. 3. При refetch выбранный элемент сохраняется, если он есть в данных. 4. No-selection state объясняет следующий шаг. | — | M |
| UXF-004 | Сделать selection-driven workspace явным для процессов | P1 | UX flow fixes | `/dashboard/processes` | Таблица, граф и detail rail слабо связаны визуально | Пользователь воспринимает экран как единое пространство вокруг выбранного процесса | 1. Выбранный процесс визуально закреплен в rail. 2. Граф и detail обновляются согласованно. 3. Refetch не сбрасывает selection без причины. 4. Placeholder без выбора объясняет следующий шаг. | — | M |
| BFX-001 | Заменить `window.confirm` на системный confirm dialog в channels | P1 | bugfix | `/channels` | Удаление и деактивация канала подтверждаются браузерным confirm без контекста и pending-state | Подтверждение действия безопасно, информативно и не выглядит как заглушка | 1. У delete/deactivate есть модалка с названием канала и текстом действия. 2. Во время submit действие блокируется. 3. После success или error пользователь получает наблюдаемый результат. | UIF-004 | M |
| BFX-002 | Заменить `window.confirm` на системный confirm dialog в jobs retry | P1 | bugfix | `/jobs` | Retry critical operations выполняется через browser confirm и не дает post-action feedback | Retry оформлен как осознанное действие с результатом | 1. Retry открывает confirm dialog с ID job или dead-letter. 2. После confirm виден row-level pending state. 3. После завершения виден success или error результат без ручного refresh. | UIF-004 | M |
| BFX-003 | Добавить observable mutation feedback в admin forms | P1 | bugfix | `/channels`, `/users`, `/settings` | После create/update не всегда ясно, что произошло | Пользователь видит progress, success и error после мутации | 1. У create/update/delete есть pending state. 2. После успеха показывается success feedback. 3. После ошибки пользователь видит error feedback без потери формы. | BFX-001 | M |
| BFX-004 | Исправить битые fallback-строки и кодировку в reports | P1 | bugfix | `/reports/*`, i18n resources | В route-коде есть mojibake в `defaultValue` | На reports нет битых строк ни при обычной локали, ни при fallback | 1. В коде и UI отсутствуют битые символы. 2. Fallback-тексты читаемы и согласованы с copy rules. 3. Проверен сценарий fallback без словаря. | — | S |
| BFX-005 | Добавить формальный read-only режим для analyst/settings и viewer surfaces | P2 | bugfix | `/settings`, viewer routes | Read-only поведение местами есть, но не всегда читается как осознанный режим | Пользователь понимает, что может смотреть, но не может менять | 1. На read-only экранах есть единый notice. 2. Mutation controls скрыты или disabled консистентно. 3. Нет экранов с мертвыми действиями без объяснения. | UIF-004 | M |
| BFX-006 | Довести stale/loading behavior без сброса контента при refetch | P1 | bugfix | dashboard, detail pages, reports | Refetch и secondary loading местами заменяют экран целиком | Уже загруженный контент остается на месте, пока идет обновление | 1. Повторный fetch не скрывает основной контент. 2. Loading при refresh отображается inline. 3. Secondary block errors не заменяют всю страницу. | CRF-005 | L |
| KG-001 | Add explicit keyword search control to posts, events and processes dashboards | P0 | UX flow fixes | `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes` | Пользователь не может сузить dashboard-данные по свободному текстовому запросу и быстро найти сущность по теме | На каждом dashboard есть единый search block с input, submit и reset; состояние поиска хранится в URL и восстанавливается после reload | 1. На каждом из трех маршрутов отображается input поиска и кнопки `Найти` и `Сбросить поиск`. 2. При вводе менее 2 символов кнопка `Найти` disabled. 3. После submit query сохраняется в URL как отдельный query param. 4. После reload страницы query восстанавливается из URL в поле ввода. 5. Нажатие `Сбросить поиск` удаляет query param из URL и возвращает экран в обычное dashboard-состояние. 6. Поиск не запускается автоматически при вводе текста без submit. | UXF-001; расширение dashboard filter parsing/serialization для нового `query` param | M |
| KG-002 | Filter posts dashboard dataset by keyword search results | P0 | UX flow fixes | `/dashboard/posts` | Даже при наличии search UI posts dashboard не умеет применить результат `/api/keyword/search/posts` к своей таблице | После успешного keyword search posts dashboard показывает только посты, чьи `post_id` вернулись из `/api/keyword/search/posts` | 1. При submit с `query >= 2` frontend вызывает `/api/keyword/search/posts`. 2. В payload передаются `query`, `limit`, `date_from/date_to`, `channel_ids` из dashboard filters. 3. Если поиск вернул `N` post ids, таблица posts dashboard отображает только строки с этими `post_id`. 4. Если найденные `post_id` не пересекаются с текущим dashboard dataset, таблица показывает empty state `По текущему запросу посты не найдены в этой выборке`. 5. Summary cards остаются от dashboard snapshot и не пересчитываются на клиенте. | KG-001; endpoint `/api/keyword/search/posts`; frontend query hook for keyword search | M |
| KG-003 | Filter events dashboard by posts matched through keyword search | P0 | UX flow fixes | `/dashboard/events` | На events dashboard нет способа найти события через связанные посты | После keyword search events dashboard показывает только события, у которых `post_ids` пересекаются с найденными постами | 1. После успешного вызова `/api/keyword/search/posts` frontend собирает set найденных `post_id`. 2. В events table остаются только строки, где `item.post_ids` содержит хотя бы один найденный `post_id`. 3. Если пересечений нет, экран показывает empty state с текстом, отличающимся от `поиск не дал постов`. 4. Если query очищен, events dashboard возвращается к полной выборке текущего snapshot. 5. Выбор события и правая панель работают только для отфильтрованных строк. | KG-002; наличие `post_ids` в `EventsDashboardItemDto`; UXF-003 | M |
| KG-004 | Define data contract for mapping keyword-matched posts to processes | P0 | bugfix | `/dashboard/processes` | `/search/posts` возвращает посты, а текущий `ProcessesDashboardResponse` не содержит явной связи `process -> post_ids` | Перед реализацией UI команда фиксирует единственный детерминированный способ маппинга search result в process rows | 1. Задокументирован один источник данных для связи найденных `post_id` с `process_id`. 2. Если используется существующий API, в задаче указан конкретный контракт и поле. 3. Если существующего контракта недостаточно, создана отдельная backend or API задача на добавление связи. 4. До появления контракта frontend implementation for `/dashboard/processes` не стартует. | backend or API contract for process-to-post mapping | S |
| KG-005 | Filter processes dashboard by keyword search using approved mapping | P1 | UX flow fixes | `/dashboard/processes` | После подтверждения контракта процессный dashboard должен поддерживать тот же поисковый паттерн, что и posts/events | После keyword search dashboard показывает только процессы, связанные с найденными постами по утвержденному mapping rule | 1. Используется только заранее утвержденный mapping contract. 2. После submit отображаются только процессы, удовлетворяющие mapping rule. 3. Если посты найдены, но процессы не сматчены, показывается `empty-mapped` state. 4. Поведение reset и URL state совпадает с posts/events. | KG-004; UXF-004 | M |
| KG-006 | Define and implement dashboard search availability rules by role and backend rollout state | P0 | bugfix | все 3 dashboard-экрана | Dashboard доступен `viewer`, но `/search/posts` недоступен `viewer`; endpoint также может вернуть `404` из-за rollout | Доступность search control детерминирована и одинакова на всех dashboards | 1. Для `admin` и `analyst` search control отображается. 2. Для `viewer` выполнено одно из двух и это зафиксировано в продуктовой постановке: control скрыт полностью или виден disabled с текстом причины. 3. При `404` от backend пользователь видит сообщение `поиск недоступен для этой учетной записи или окружения`. 4. При `403` пользователь видит сообщение `поиск недоступен для вашей роли`. | product decision по поведению для `viewer`; KG-001 | S |
| KG-007 | Add automated coverage for dashboard keyword search | P0 | bugfix | frontend test suite | Без тестов легко сломать URL state, RBAC, mapping logic и error states | Поведение поиска покрыто интеграционными тестами на уровне screen/routes | 1. Есть тест на submit search и вызов `/api/keyword/search/posts` на `/dashboard/posts`. 2. Есть тест на client-side filtering rows на `/dashboard/posts`. 3. Есть тест на mapping в `/dashboard/events`. 4. Есть тест на `viewer` behavior. 5. Есть тест на `404` unavailable state. 6. Есть тест на `reset search`. 7. Есть тест на восстановление search state из URL. | KG-002, KG-003, KG-006; CRF-002 | M |
| STG-001 | Replace JSON-first settings screen with category-based settings architecture | P0 | UX flow fixes | `/settings` | Текущий экран организован вокруг raw JSON, а не вокруг задач администратора | Экран настроек разбит на тематические категории, каждая категория открывает форму только для связанных параметров | 1. На экране отображаются 8 категорий на основе backend scopes: `ingest`, `reports`, `retention`, `jobs`, `api`, `scheduler`, `monitor`, `features`. 2. Категории отображаются в отдельной navigation area. 3. При выборе категории в контентной области показываются только поля выбранного scope. 4. По умолчанию открывается первая доступная категория или категория из URL. 5. Текущая выбранная категория сохраняется в URL query param, например `?section=jobs`. | existing settings scopes from backend; CRF-005 | M |
| STG-002 | Introduce frontend metadata registry for settings fields | P0 | component refactor | `/settings` | Backend keys непонятны администратору без технического контекста | Каждое поле имеет локализованный label, description, unit, control type и hint | 1. Для каждого поля из canonical settings defaults существует metadata entry. 2. Metadata entry содержит technical key, human label RU, optional EN, description RU, input type, unit if applicable, sort order. 3. Отсутствие metadata для поля приводит к явному fallback rendering. 4. Technical key отображается как secondary text, а не как primary label. | canonical settings keys from backend | M |
| STG-003 | Implement typed settings form per scope instead of JSON textarea | P0 | UX flow fixes | `/settings` | JSON textarea делает изменение одной настройки медленным и рискованным | Для выбранной категории пользователь редактирует параметры через типизированные поля, не видя JSON как основной способ редактирования | 1. Boolean fields рендерятся как switch или checkbox. 2. Integer and float fields рендерятся как numeric inputs. 3. Percent-like fields отображают unit рядом с input. 4. Для каждого поля показывается текущее effective value. 5. Для каждого поля отображается default value. 6. `textarea` с raw JSON не является primary editing control на основном экране. 7. Save отправляет `PUT /api/settings/{scope}` с полным payload scope. | STG-002; existing `PUT /api/settings/{key}` | L |
| STG-004 | Add field-level validation aligned with backend settings constraints | P0 | bugfix | `/settings` | Сейчас UI проверяет только валидный JSON-объект, а не смысловые ограничения отдельных полей | Пользователь получает ошибку на уровне конкретного поля до отправки формы | 1. Для всех полей в UI отражены min/max constraints из backend validation. 2. Save blocked when at least one field is invalid. 3. Error message показывается рядом с полем. 4. Ошибка `422` от backend маппится в field-level или section-level error. 5. Client validation и backend validation не расходятся по диапазонам для известных полей. | STG-003; `services/settings_validation.py` | M |
| STG-005 | Add search and filtering inside settings | P1 | UX flow fixes | `/settings` | При росте числа параметров админу сложно находить нужную настройку внутри категорий | Пользователь может найти настройку по русскому названию, technical key или description | 1. На экране есть search input. 2. Search фильтрует список полей в реальном времени. 3. Search работает по human label, technical key и description. 4. При отсутствии совпадений показывается dedicated empty state. 5. Search не меняет сохраненные значения и не вызывает API. | STG-002 | S |
| STG-006 | Prevent silent loss of settings edits | P0 | bugfix | `/settings` | При category switch, route change или reload админ может потерять изменения без предупреждения | При наличии несохраненных изменений пользователь получает явное предупреждение | 1. При изменении хотя бы одного поля форма получает dirty state. 2. При смене категории с dirty state показывается confirm dialog. 3. При уходе со страницы или route change с dirty state показывается confirm dialog. 4. После успешного сохранения dirty state сбрасывается. 5. Save относится только к выбранной категории. | STG-003 | M |
| STG-007 | Keep analyst settings access read-only with structured presentation | P1 | UX flow fixes | `/settings` | У аналитика есть доступ к effective settings, но current UI показывает technical payload, а не понятную структуру | Аналитик видит те же категории и поля, но без возможности редактирования | 1. Для `analyst` не отображаются save controls. 2. Для `analyst` поля рендерятся в read-only mode. 3. Аналитик может переключать категории и просматривать effective values. 4. Raw effective JSON может быть доступен как secondary technical panel, но не как основной контент. | existing RBAC; STG-001; BFX-005 | M |
| STG-008 | Keep raw JSON view as secondary advanced tool | P2 | polish | `/settings` | Иногда администратору нужен inspect/debug payload, но это не должен быть основной UX | Raw JSON доступен только как advanced disclosure block | 1. Основной edit flow не использует JSON textarea. 2. Raw JSON hidden by default. 3. Raw JSON доступен через explicit `Technical details` или `Show raw payload`. 4. В advanced block нет primary CTA, который конкурирует с structured form. | STG-003 | S |
| STG-009 | Add screen-level tests for structured settings editing | P0 | bugfix | frontend test suite | Без тестов легко сломать RBAC, validation, dirty-state protection и payload mapping | Новый settings flow покрыт тестами на route/screen level | 1. Есть тест на render category navigation. 2. Есть тест на field rendering by type. 3. Есть тест на client-side validation. 4. Есть тест на save payload for one scope. 5. Есть тест на unsaved changes confirm. 6. Есть тест на analyst read-only mode. 7. Есть тест на search or filter. | STG-001, STG-003, STG-004, STG-006, STG-007; CRF-002 | M |
| UXF-005 | Пересобрать keyword graph в пошаговый workflow | P1 | UX flow fixes | `/keyword-graph` | Экран перегружен длинной формой и слабо ведет пользователя по сценарию | Экран ведет пользователя по цепочке: search -> select seed -> build -> inspect -> report | 1. На экране явно видны этапы workflow. 2. Пока не выполнен предыдущий шаг, следующий disabled или объяснен. 3. После поиска пользователь сразу видит, что выбрать для seed set. 4. Build/report actions не теряются в боковой колонке. | UIF-001 | L |
| POL-001 | Сжать admin CRUD layout и убрать гигантские капсульные кнопки | P2 | polish | `/channels`, `/users` | Формы и действия визуально непропорциональны и выглядят как мокап | Admin UI выглядит как рабочая консоль | 1. Кнопки не занимают чрезмерную площадь. 2. Форма редактирования не разваливает боковую колонку. 3. На одном экране читается один primary action. | UIF-004 | S |
| POL-002 | Сделать graph panels компактнее и информативнее | P2 | polish | events/processes graph panels | Графы и связанные карточки избыточно вертикальны и шумны | Пользователь быстрее считывает структуру графа и связи | 1. Граф, summary и related items помещаются компактнее. 2. Secondary metadata не доминирует над основным названием или связью. 3. No-edges state выглядит как штатный исход. | UXF-003, UXF-004 | M |
| UXF-006 | Добавить явные next-step actions в related posts секцию event graph panel | P1 | UX flow fixes | `/dashboard/events` graph panel | В related posts пользователь видит карточки постов, но не получает явного следующего шага и может не понять, как перейти к исходному материалу | Каждый related post дает очевидное действие перехода к посту, а root post читается как главный источник контекста | 1. В каждой карточке related post есть явный `Open post` action или сама карточка имеет очевидный clickable affordance. 2. Root post визуально отличим и не теряется среди остальных карточек. 3. С клавиатуры можно последовательно дойти до перехода по каждому related post. 4. В no-edges сценарии related posts секция остается полезной и navigable. | POL-002 | S |
| POL-006 | Нормализовать compact toolbar и hierarchy controls в graph panels | P2 | polish | events/processes graph panels | После уплотнения панелей toolbar actions все еще выглядят как крупные dashboard-кнопки и конфликтуют с compact card layout | Toolbar читается как вторичный набор lightweight controls внутри graph workspace | 1. Reset и reload визуально слабее page-level primary CTA и не выглядят как главные действия экрана. 2. На event и process graph toolbar используется единый button style, spacing и disabled state. 3. На ширине 1024px и 768px toolbar meta и controls не наезжают друг на друга и читаются по строкам. 4. Во время loading disabled state различим визуально без потери читаемости. | POL-002; POL-003 | S |
| POL-007 | Убрать дублирование заголовков и повторяющегося контекста в graph panels | P2 | polish | events/processes graph panels | Один и тот же selected title и контекст повторяются в panel header, toolbar, summary и section header, из-за чего экран выглядит многословным и менее собранным | У панели есть один главный title-level контекст, а секции добавляют только новую информацию | 1. В каждой graph panel выбранная сущность отображается один раз как primary heading. 2. Summary и canvas section не повторяют тот же title без новой информации. 3. На desktop первый экран панели становится короче минимум на один текстовый блок по сравнению с текущим состоянием. 4. Event и process graph panels используют одинаковую hierarchy pattern для header -> summary -> sections. | POL-002 | S |
| POL-008 | Пересобрать visual priority secondary metadata в graph cards и edge lists | P2 | polish | events/processes graph panels | Secondary metadata сведена к одинаковым pills, поэтому status, date, score и counters местами снова конкурируют с названием сущности или связи | Secondary metadata помогает сканировать карточки, но не перетягивает внимание с title и relation | 1. В node/event/edge card title или relation визуально сильнее любого secondary мета-элемента. 2. Не вся metadata рендерится одинаковыми pills: low-priority info отображается как muted inline text или compact meta row. 3. По edge list можно быстро считать направление и тип связи без необходимости читать все meta badges. 4. Для event и process graph cards применены одинаковые правила visual priority. | POL-002 | M |
| CRF-006 | Вынести shared graph-panel primitives для summary, section header и inline states | P2 | component refactor | events/processes graph panels | Compact graph panel layout реализован дублирующимся JSX и CSS в event/process вариантах, из-за чего паттерн может быстро разъехаться и выглядеть как локальная заплатка | Event и process graph panels собираются из общих layout primitives и развиваются без copy-paste drift | 1. Event и process graph panels используют общий primitive или единый reusable pattern для summary block, section shell и inline empty state. 2. Базовые spacing и state styles не дублируются отдельно в каждом panel implementation. 3. Добавление новой graph panel не требует копировать существующую структуру секций вручную. 4. Текущие event/process route tests проходят без визуально значимого regression fix в каждом panel по отдельности. | POL-002; POL-006; POL-007; POL-008 | M |
| POL-003 | Улучшить mobile/tablet layout для filters и side rails | P2 | polish | dashboard, reports, keyword graph, admin | Текущий responsive в основном просто схлопывает grid, но не пересобирает сценарий | На tablet/mobile ключевые действия и фильтры остаются управляемыми | 1. На ширине 768px фильтры не образуют хаотичную простыню. 2. Side rails переходят в предсказуемый stack order. 3. Таблицы остаются читаемыми или получают mobile-specific presentation. | UIF-001, CRF-001 | L |
| POL-004 | Добавить row-level hover, focus и selected consistency | P3 | polish | все таблицы | Hover, selected и focus states несистемны и местами слабо видны | Таблицы дают ясную обратную связь при наведении, фокусе и выборе | 1. Hover, selected и focus различимы визуально. 2. Выбранная строка не теряется среди hover-эффектов. 3. Keyboard focus виден на интерактивных ячейках и действиях. | CRF-001, UIF-005 | S |
| POL-005 | Добавить accessible graph summary fallback | P3 | polish | event/process graph panels | Canvas сам по себе не является достаточной альтернативой для всех пользователей | У графов есть компактное текстовое summary и доступный список связей | 1. У каждого graph panel есть текстовый summary количества узлов, ребер и ключевых связей. 2. Список узлов и связей доступен без чтения canvas. 3. Summary обновляется при смене selection. | POL-002 | S |

## Preserved Sequence Notes

### Dashboard Keyword Search

Встроенные задачи `KG-001` ... `KG-007` идут в том же порядке, что и в `docs/dashboard_keyword_search_backlog.md`:

1. сначала общий UX и URL state
2. затем posts integration
3. затем events mapping
4. затем contract validation для processes
5. затем implementation для processes
6. затем RBAC/rollout alignment
7. затем tests

В общую очередь они встроены без нарушения внутреннего порядка.

### Settings Redesign

Встроенные задачи `STG-001` ... `STG-009` идут в том же порядке, что и в `docs/settings_redesign_backlog.md`:

1. architecture
2. metadata layer
3. typed form
4. validation
5. search
6. unsaved changes protection
7. analyst read-only mode
8. advanced raw JSON fallback
9. tests

В общую очередь они встроены без нарушения внутреннего порядка.

## Recommended Implementation Order

### Wave 1: Core foundation

1. `UIF-001`
2. `CRF-001`
3. `CRF-002`
4. `UXF-001`
5. `UXF-002`

### Wave 2: Dashboard analytical flows

6. `UXF-003`
7. `UXF-004`
8. `BFX-006`
9. `KG-001`
10. `KG-002`
11. `KG-003`
12. `KG-006`
13. `KG-004`
14. `KG-005`
15. `KG-007`

### Wave 3: Settings redesign

16. `STG-001`
17. `STG-002`
18. `STG-003`
19. `STG-004`
20. `STG-006`
21. `STG-007`
22. `STG-005`
23. `STG-008`
24. `STG-009`

### Wave 4: Admin and operations quality

25. `UIF-002`
26. `UIF-003`
27. `UIF-004`
28. `UIF-005`
29. `BFX-001`
30. `BFX-003`
31. `BFX-002`
32. `BFX-004`
33. `BFX-005`
34. `CRF-003`
35. `CRF-004`
36. `CRF-005`

### Wave 5: Specialized workflow and polish

37. `UXF-005`
38. `POL-001`
39. `POL-002`
40. `UXF-006`
41. `POL-006`
42. `POL-007`
43. `POL-008`
44. `CRF-006`
45. `POL-003`
46. `POL-004`
47. `POL-005`

