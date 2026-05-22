import re

def process_file(file_path, replacements):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

admin_panel_replacements = [
    ('{% block title %}Админ панель{% endblock %}', '{% block title %}{% translate "Админ панель" %}{% endblock %}'),
    ('{% block page_title %}Админ панель{% endblock %}', '{% block page_title %}{% translate "Админ панель" %}{% endblock %}'),
    ('Управление рабочими настройками базы без Django admin.', '{% translate "Управление рабочими настройками базы без Django admin." %}'),
    ('<div class="text-muted small mb-2">Клиенты</div>', '<div class="text-muted small mb-2">{% translate "Клиенты" %}</div>'),
    ('<div class="text-muted small mb-2">Основания подачи</div>', '<div class="text-muted small mb-2">{% translate "Основания подачи" %}</div>'),
    ('<div class="text-muted small mb-2">Открытые задачи</div>', '<div class="text-muted small mb-2">{% translate "Открытые задачи" %}</div>'),
    ('<div class="text-muted small mb-2">Ожидают оплаты</div>', '<div class="text-muted small mb-2">{% translate "Ожидают оплаты" %}</div>'),
    ('<h5 class="card-title">Шаблоны</h5>', '<h5 class="card-title">{% translate "Шаблоны" %}</h5>'),
    ('<p class="text-muted">Глобальные значения для печатных документов текущей базы.</p>', '<p class="text-muted">{% translate "Глобальные значения для печатных документов текущей базы." %}</p>'),
    ('<a href="{% url \'clients:document_template_hub\' %}" class="btn btn-primary">Открыть</a>', '<a href="{% url \'clients:document_template_hub\' %}" class="btn btn-primary">{% translate "Открыть" %}</a>'),
    ('<h5 class="card-title">Чеклисты</h5>', '<h5 class="card-title">{% translate "Чеклисты" %}</h5>'),
    ('<p class="text-muted">Обязательные документы и структура checklist по типу подачи.</p>', '<p class="text-muted">{% translate "Обязательные документы и структура checklist по типу подачи." %}</p>'),
    ('<a href="{% url \'clients:document_checklist_manage\' %}" class="btn btn-primary">Открыть</a>', '<a href="{% url \'clients:document_checklist_manage\' %}" class="btn btn-primary">{% translate "Открыть" %}</a>'),
    ('<h5 class="card-title">Основания подачи</h5>', '<h5 class="card-title">{% translate "Основания подачи" %}</h5>'),
    ('<p class="text-muted">Список submission types, статусы и локализованные названия в рабочем интерфейсе.</p>', '<p class="text-muted">{% translate "Список submission types, статусы и локализованные названия в рабочем интерфейсе." %}</p>'),
    ('<a href="{% url \'clients:submission_manage\' %}" class="btn btn-primary">Открыть</a>', '<a href="{% url \'clients:submission_manage\' %}" class="btn btn-primary">{% translate "Открыть" %}</a>'),
    ('<h5 class="card-title">Цены и услуги</h5>', '<h5 class="card-title">{% translate "Цены и услуги" %}</h5>'),
    ('<p class="text-muted mb-2">Рабочий прайс без Django admin.</p>', '<p class="text-muted mb-2">{% translate "Рабочий прайс без Django admin." %}</p>'),
    ('<div class="small text-muted mb-3">Записей: {{ total_service_prices }}. Сумма прайса: {{ total_price_sum }} PLN</div>', '<div class="small text-muted mb-3">{% translate "Записей:" %} {{ total_service_prices }}. {% translate "Сумма прайса:" %} {{ total_price_sum }} PLN</div>'),
    ('<a href="{% url \'clients:service_price_manage\' %}" class="btn btn-primary">Открыть</a>', '<a href="{% url \'clients:service_price_manage\' %}" class="btn btn-primary">{% translate "Открыть" %}</a>'),
    ('<h5 class="card-title">Сотрудники</h5>', '<h5 class="card-title">{% translate "Сотрудники" %}</h5>'),
    ('<p class="text-muted">Управление staff-аккаунтами, доступом и рабочими ролями.</p>', '<p class="text-muted">{% translate "Управление staff-аккаунтами, доступом и рабочими ролями." %}</p>'),
    ('<a href="{% url \'clients:staff_manage\' %}" class="btn btn-primary">Открыть</a>', '<a href="{% url \'clients:staff_manage\' %}" class="btn btn-primary">{% translate "Открыть" %}</a>'),
    ('<a href="{% url \'clients:role_manage\' %}" class="btn btn-outline-secondary ms-2">Роли</a>', '<a href="{% url \'clients:role_manage\' %}" class="btn btn-outline-secondary ms-2">{% translate "Роли" %}</a>'),
    ('<h5 class="card-title">Система</h5>', '<h5 class="card-title">{% translate "Система" %}</h5>'),
    ('<p class="text-muted">Техническое состояние, runtime checks и health dashboard.</p>', '<p class="text-muted">{% translate "Техническое состояние, runtime checks и health dashboard." %}</p>'),
    ('<h5 class="card-title">Метрики</h5>', '<h5 class="card-title">{% translate "Метрики" %}</h5>'),
    ('<p class="text-muted">Быстрый переход к аналитике и воронке.</p>', '<p class="text-muted">{% translate "Быстрый переход к аналитике и воронке." %}</p>'),
    ('<a href="{% url \'clients:metrics_dashboard\' %}" class="btn btn-outline-secondary">Метрики</a>', '<a href="{% url \'clients:metrics_dashboard\' %}" class="btn btn-outline-secondary">{% translate "Метрики" %}</a>'),
    ('<h5 class="card-title">Журналы системы</h5>', '<h5 class="card-title">{% translate "Журналы системы" %}</h5>'),
    ('<p class="text-muted">Просмотр отправленных писем и действий сотрудников (логи аудита).</p>', '<p class="text-muted">{% translate "Просмотр отправленных писем и действий сотрудников (логи аудита)." %}</p>')
]
process_file('clients/templates/clients/admin_panel.html', admin_panel_replacements)

submission_manage_replacements = [
    ('<a href="{% url \'clients:admin_panel\' %}" class="btn btn-outline-secondary">Админ панель</a>', '<a href="{% url \'clients:admin_panel\' %}" class="btn btn-outline-secondary">{% translate "Админ панель" %}</a>'),
    ('<h5 class="mb-3">Создать новое основание</h5>', '<h5 class="mb-3">{% translate "Создать новое основание" %}</h5>'),
    ('<label for="{{ create_form.name.id_for_label }}" class="form-label">Название (внутреннее)</label>', '<label for="{{ create_form.name.id_for_label }}" class="form-label">{% translate "Название (внутреннее)" %}</label>'),
    ('<label for="{{ create_form.status.id_for_label }}" class="form-label">Статус</label>', '<label for="{{ create_form.status.id_for_label }}" class="form-label">{% translate "Статус" %}</label>'),
    ('<button type="submit" class="btn btn-primary">Создать</button>', '<button type="submit" class="btn btn-primary">{% translate "Создать" %}</button>'),
    ('<h5 class="mb-3">Существующие основания</h5>', '<h5 class="mb-3">{% translate "Существующие основания" %}</h5>'),
    ('<th>Слаг</th>', '<th>{% translate "Слаг" %}</th>'),
    ('<th>Статус</th>', '<th>{% translate "Статус" %}</th>'),
    ('<th class="text-end">Действия</th>', '<th class="text-end">{% translate "Действия" %}</th>'),
    ('<button type="submit" form="update-submission-{{ submission.id }}" class="btn btn-sm btn-outline-primary">Сохранить</button>', '<button type="submit" form="update-submission-{{ submission.id }}" class="btn btn-sm btn-outline-primary">{% translate "Сохранить" %}</button>'),
    ('<form method="post" class="d-inline" onsubmit="return confirm(\'Удалить это основание?\');">', '<form method="post" class="d-inline" onsubmit="return confirm(\'{% translate \"Удалить это основание?\" %}\');">'),
    ('<button type="submit" class="btn btn-sm btn-outline-danger">Удалить</button>', '<button type="submit" class="btn btn-sm btn-outline-danger">{% translate "Удалить" %}</button>'),
    ('<td colspan="7" class="text-center text-muted py-4">Нет добавленных оснований.</td>', '<td colspan="7" class="text-center text-muted py-4">{% translate "Нет добавленных оснований." %}</td>')
]
process_file('clients/templates/clients/submission_manage.html', submission_manage_replacements)

service_price_replacements = [
    ('{% block title %}Цены и услуги{% endblock %}', '{% block title %}{% translate "Цены и услуги" %}{% endblock %}'),
    ('{% block page_title %}Цены и услуги{% endblock %}', '{% block page_title %}{% translate "Цены и услуги" %}{% endblock %}'),
    ('{% block page_subtitle %}Управление ценами на услуги.{% endblock %}', '{% block page_subtitle %}{% translate "Управление ценами на услуги." %}{% endblock %}'),
    ('<a href="{% url \'clients:admin_panel\' %}" class="btn btn-outline-secondary">Админ панель</a>', '<a href="{% url \'clients:admin_panel\' %}" class="btn btn-outline-secondary">{% translate "Админ панель" %}</a>'),
    ('<th>Описание</th>', '<th>{% translate "Описание" %}</th>'),
    ('<th style="width: 220px;">Цена PLN</th>', '<th style="width: 220px;">{% translate "Цена PLN" %}</th>'),
    ('<button type="submit" class="btn btn-primary">Сохранить изменения</button>', '<button type="submit" class="btn btn-primary">{% translate "Сохранить изменения" %}</button>')
]
process_file('clients/templates/clients/service_price_manage.html', service_price_replacements)

print("Files updated")
