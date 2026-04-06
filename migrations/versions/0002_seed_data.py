"""Seed data: permissions, roles, role_permissions, surveys, triggers, ui_texts.

All INSERTs are idempotent (ON CONFLICT DO NOTHING / WHERE NOT EXISTS).

Revision ID: 0002_seed
Revises: 0001_baseline
Create Date: 2026-04-06 00:00:01.000000
"""

import json
from datetime import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_seed"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Seed data ───────────────────────────────────────────────────────────

PERMISSIONS = [
    ("all_permissions", "Полный доступ ко всем функциям"),
    ("manage_users", "Управление пользователями"),
    ("manage_cohorts", "Управление когортами"),
    ("manage_roles", "Управление ролями и пермишенами"),
    ("manage_surveys", "Управление шаблонами опросов"),
    ("manage_triggers", "Управление триггерными правилами"),
    ("send_manual", "Ручная и отложенная отправка"),
    ("update_user_role", "Изменение роли пользователя"),
    ("update_user_mentor", "Назначение ментора"),
    ("update_user_cohort", "Назначение когорты"),
    ("update_user_state", "Изменение состояния пользователя"),
    ("view_students", "Просмотр списка менти"),
    ("manage_meetings", "Управление встречами"),
    ("view_own_meetings", "Просмотр своих встреч"),
    ("view_own_info", "Просмотр своей информации"),
    ("end_call", "Завершение активного созвона"),
    ("fill_survey", "Заполнение опросов"),
    ("fill_self_review", "Заполнение самооценки"),
    ("view_direction_students", "Просмотр менти своего направления"),
    ("receive_direction_notifications", "Получение уведомлений по направлению"),
    ("send_direction_notification", "Отправка уведомлений менти направления"),
    ("view_job_search_reports", "Просмотр отчётов по поиску работы"),
    ("view_education_feedback", "Просмотр обратной связи о сопровождении"),
    ("export_job_search", "Экспорт отчётов по поиску работы"),
    ("export_education_feedback", "Экспорт обратной связи о сопровождении"),
    ("update_student_status", "Обновление статуса менти (ментором)"),
    ("mentor_role", "Marker: user has mentor capabilities"),
    ("view_referral_link", "Просмотр реферальной ссылки"),
    ("manage_channel_links", "Управление канальными ссылками"),
    ("propose_meetings", "Предложить встречу ментору"),
]

ROLES = [
    {"name": "admin", "display_name": "Админ"},
    {"name": "mentor", "display_name": "Ментор"},
    {"name": "student", "display_name": "Менти"},
    {"name": "direction_lead", "display_name": "Лид направления"},
    {"name": "job_search_lead", "display_name": "Ответственный за поиск работы"},
    {"name": "education_lead", "display_name": "Ответственный за сопровождение"},
]

MENTOR_PERMS = [
    "view_students",
    "manage_meetings",
    "view_own_meetings",
    "view_own_info",
    "end_call",
    "fill_survey",
    "fill_self_review",
    "update_student_status",
    "mentor_role",
]

ROLE_PERMISSIONS_MAP = {
    "admin": ["all_permissions"],
    "mentor": MENTOR_PERMS + ["view_referral_link"],
    "student": [
        "view_own_meetings",
        "view_own_info",
        "fill_survey",
        "view_referral_link",
        "propose_meetings",
    ],
    "direction_lead": MENTOR_PERMS
    + [
        "view_direction_students",
        "receive_direction_notifications",
        "view_referral_link",
    ],
    "job_search_lead": MENTOR_PERMS
    + ["view_job_search_reports", "export_job_search", "view_referral_link"],
    "education_lead": MENTOR_PERMS
    + ["view_education_feedback", "export_education_feedback", "view_referral_link"],
}

# All rating questions use max=10 (final state after 0015)
TEMPLATES = [
    {
        "slug": "post_call_student",
        "title": "Опрос менти после созвона",
        "description": "Заполняется менти после завершённого созвона с ментором",
        "questions": [
            {
                "sort_order": 1,
                "title": "Стиль общения ментора",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Глубина проверки знаний",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Насколько менти усвоил(а) материал",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Комментарий",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "mentor_feedback",
        "title": "Фидбек ментора после созвона",
        "description": "Заполняется ментором после завершённого созвона с менти",
        "questions": [
            {
                "sort_order": 1,
                "title": "Готовность менти",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "not_ready", "label": "Не готов"},
                    {"value": "bad", "label": "Плохо"},
                    {"value": "ok", "label": "Нормально"},
                    {"value": "great", "label": "Отлично"},
                ],
            },
            {
                "sort_order": 2,
                "title": "Мотивация менти",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Стадия нейромутации",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Комментарий",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "mentor_self_review",
        "title": "Двухнедельный опрос ментора",
        "description": "Заполняется ментором раз в две недели",
        "questions": [
            {
                "sort_order": 1,
                "title": "Загруженность",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Удовлетворённость (NPS)",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Рутина",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Ясность ожиданий",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 5,
                "title": "Поддержка и доступность руководства/коллег",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 6,
                "title": "Что одно мы могли бы улучшить?",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "greeting_mentee_feedback",
        "title": "Опрос менти после первого созвона",
        "description": "Заполняется менти через 24 часа после первого созвона (стадия greeting)",
        "questions": [
            {
                "sort_order": 1,
                "title": "Насколько понятны условия сопровождения",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Впечатление от встречи с ментором",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Уверенность в выборе направления",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Что повлияло на решение начать/не начать сопровождение?",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "greeting_mentor_feedback",
        "title": "Опрос ментора после первого созвона",
        "description": "Заполняется ментором через 24 часа после первого созвона (стадия greeting)",
        "questions": [
            {
                "sort_order": 1,
                "title": "Мотивация менти",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Реалистичность ожиданий менти",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Рекомендуешь ли брать в работу?",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "yes", "label": "Да"},
                    {"value": "no", "label": "Нет"},
                ],
            },
            {
                "sort_order": 4,
                "title": "Комментарий к рекомендации",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "weekly_mentee_study",
        "title": "Еженедельный опрос менти (Study)",
        "description": "Заполняется менти еженедельно в период сопровождения (Study)",
        "questions": [
            {
                "sort_order": 1,
                "title": "Оценка ментора",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Понятность материала / roadmap",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Ощущение прогресса",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Что было самым полезным за неделю?",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
            {
                "sort_order": 5,
                "title": "Что хочешь изменить?",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "weekly_mentee_search",
        "title": "Еженедельный опрос менти (Search)",
        "description": "Заполняется менти еженедельно в период поиска работы (Search)",
        "questions": [
            {
                "sort_order": 1,
                "title": "Количество прожатых откликов (за неделю)",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Количество скринингов (за неделю)",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Количество техничек (за неделю)",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Количество оферов (за неделю)",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "weekly_mentor_per_student",
        "title": "Еженедельный опрос ментора по менти",
        "description": "Заполняется ментором еженедельно на каждого менти в стадии Study",
        "questions": [
            {
                "sort_order": 1,
                "title": "Вовлечённость менти",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Выполнение заданий",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Готовность к следующему этапу (%)",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 100},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Есть ли проблемы, требующие внимания?",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "yes", "label": "Да"},
                    {"value": "no", "label": "Нет"},
                ],
            },
            {
                "sort_order": 5,
                "title": "Опишите проблемы",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "search_mentee_biweekly",
        "title": "Двухнедельный опрос менти (Search)",
        "description": "Заполняется менти раз в две недели в период поиска работы (search)",
        "questions": [
            {
                "sort_order": 1,
                "title": "Поддержка ментора при поиске работы",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Уверенность на собеседованиях",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Качество подготовки резюме и легенды",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Что помогает в поиске?",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
            {
                "sort_order": 5,
                "title": "Что мешает или чего не хватает?",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "search_mentor_biweekly",
        "title": "Двухнедельный опрос ментора по менти (Search)",
        "description": "Заполняется ментором раз в две недели на каждого менти в стадии search",
        "questions": [
            {
                "sort_order": 1,
                "title": "Активность менти в поиске",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Качество откликов и подготовки к собеседованиям",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Готовность получить оффер",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "10", "label": "10%"},
                    {"value": "20", "label": "20%"},
                    {"value": "30", "label": "30%"},
                    {"value": "40", "label": "40%"},
                    {"value": "50", "label": "50%"},
                    {"value": "60", "label": "60%"},
                    {"value": "70", "label": "70%"},
                    {"value": "80", "label": "80%"},
                    {"value": "90", "label": "90%"},
                    {"value": "100", "label": "100%"},
                ],
            },
            {
                "sort_order": 4,
                "title": "Есть ли проблемы, требующие внимания?",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "yes", "label": "Да"},
                    {"value": "no", "label": "Нет"},
                ],
            },
            {
                "sort_order": 5,
                "title": "Опишите проблему",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "probation_mentee_biweekly",
        "title": "Двухнедельный опрос менти (Probationary period)",
        "description": "Заполняется менти раз в две недели во время испытательного срока",
        "questions": [
            {
                "sort_order": 1,
                "title": "Насколько ментор помогает вам адаптироваться?",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Насколько вы уверенно чувствуете себя на рабочем месте?",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Насколько работа соответствует вашим ожиданиям?",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 4,
                "title": "Какие сложности вы испытываете на работе?",
                "question_type": "text",
                "is_required": True,
                "config": None,
                "options": [],
            },
            {
                "sort_order": 5,
                "title": "Нужна ли вам дополнительная поддержка? Если да, какая?",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
    {
        "slug": "probation_mentor_biweekly",
        "title": "Двухнедельный опрос ментора по менти (Probationary period)",
        "description": "Заполняется ментором раз в две недели на каждого менти на испытательном сроке",
        "questions": [
            {
                "sort_order": 1,
                "title": "Как проходит адаптация менти на рабочем месте?",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 2,
                "title": "Насколько менти самостоятелен(на) в работе?",
                "question_type": "rating",
                "is_required": True,
                "config": {"min": 1, "max": 10},
                "options": [],
            },
            {
                "sort_order": 3,
                "title": "Оцените риск непрохождения испытательного срока",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "10", "label": "10%"},
                    {"value": "20", "label": "20%"},
                    {"value": "30", "label": "30%"},
                    {"value": "40", "label": "40%"},
                    {"value": "50", "label": "50%"},
                    {"value": "60", "label": "60%"},
                    {"value": "70", "label": "70%"},
                    {"value": "80", "label": "80%"},
                    {"value": "90", "label": "90%"},
                    {"value": "100", "label": "100%"},
                ],
            },
            {
                "sort_order": 4,
                "title": "Есть ли проблемы, требующие внимания?",
                "question_type": "single_choice",
                "is_required": True,
                "config": None,
                "options": [
                    {"value": "yes", "label": "Да"},
                    {"value": "no", "label": "Нет"},
                ],
            },
            {
                "sort_order": 5,
                "title": "Опишите проблемы или оставьте комментарий",
                "question_type": "text",
                "is_required": False,
                "config": None,
                "options": [],
            },
        ],
    },
]

NOTIFY_TEXT = "<b>Вам назначен созвон.</b>\nПодробности можно узнать в меню бота."
REMINDER_TEXT = "<b>Напоминание о созвоне через ~5 минут.</b>\nПодготовьтесь к встрече."

LEAD_TO_STUDY_TEXT = (
    "Добро пожаловать в Голубятню! 🎉\n\n"
    "Ты подключён(а) к программе сопровождения.\n\n"
    "Вступай в чаты:\n"
    "— Общий чат: $general_chat_link\n"
    "— Канал ментора: $mentor_channel_link"
)

UI_TEXTS = [
    # ── Menu ──
    ("menu.title", "Список доступных команд", "Main menu title"),
    ("menu.access_denied", "Доступ запрещен.", "Access denied message"),
    ("menu.btn.users", "👥 Пользователи", "Menu button: users"),
    ("menu.btn.cohorts", "📂 Когорты", "Menu button: cohorts"),
    ("menu.btn.surveys", "📝 Опросы", "Menu button: surveys"),
    ("menu.btn.triggers", "⚡ Триггеры", "Menu button: triggers"),
    ("menu.btn.roles", "🛡 Роли", "Menu button: roles"),
    (
        "menu.btn.mentor_stats",
        "📊 Статистика менторов",
        "Menu button: mentor stats",
    ),
    ("menu.btn.students", "🎓 Менти", "Menu button: students (mentor)"),
    ("menu.btn.meetings", "📅 Созвоны", "Menu button: meetings (mentor)"),
    ("menu.btn.my_info", "ℹ️ Обо мне", "Menu button: my info (mentor)"),
    (
        "menu.btn.my_meetings",
        "📅 Назначенные созвоны",
        "Menu button: my meetings (student)",
    ),
    (
        "menu.btn.my_info_student",
        "ℹ️ Информация обо мне",
        "Menu button: my info (student)",
    ),
    ("menu.back", "⬅️ Назад к меню", "Back to menu button"),
    (
        "menu.btn.propose_meeting",
        "📅 Предложить созвон",
        "Menu: student propose meeting btn",
    ),
    # ── Submenu titles ──
    ("menu.users.title", "👥 Меню Пользователей", "Users submenu title"),
    ("menu.cohorts.title", "📂 Меню Когорт", "Cohorts submenu title"),
    ("menu.meetings.title", "📅 Созвоны:", "Meetings submenu title"),
    ("menu.students.title", "🎓 Менти:", "Students submenu title"),
    # ── Mentor students ──
    ("menu.students.empty", "Список менти пуст.", "Empty students list"),
    ("menu.students.header", "<b>Мои менти:</b>", "Students list header"),
    (
        "menu.mentor_students.btn.list",
        "Список менти",
        "Mentor: students list btn",
    ),
    (
        "menu.mentor_students.btn.update",
        "Изменить статус менти",
        "Mentor: update student btn",
    ),
    # ── Mentor meetings ──
    (
        "menu.mentor_meetings.btn.list",
        "Список созвонов",
        "Mentor: meetings list btn",
    ),
    (
        "menu.mentor_meetings.btn.create",
        "Добавить созвон",
        "Mentor: create meeting btn",
    ),
    (
        "menu.mentor_meetings.btn.end_call",
        "Завершить активный созвон",
        "Mentor: end call btn",
    ),
    (
        "menu.mentor_meetings.btn.feedback",
        "Заполнить фидбек",
        "Mentor: fill feedback btn",
    ),
    # ── Call end messages ──
    ("menu.no_active_call", "У вас нет активного созвона.", "No active call"),
    (
        "menu.call_ended.no_meeting",
        "✅ Активный созвон завершён.\nНачало: $start\nКонец: $end",
        "Call ended (no meeting)",
    ),
    (
        "menu.call_ended.with_meeting",
        "✅ Созвон по встрече #$id завершён.\nНачало: $start\nКонец: $end\nДлительность: $duration\n\nТеперь можно заполнить фидбек.",
        "Call ended (with meeting)",
    ),
    # ── Profile ──
    ("menu.not_found", "Профиль не найден.", "Profile not found"),
    ("menu.me.title", "<b>Моя информация:</b>", "Profile title"),
    ("menu.mentor_me.btn.stats", "Моя статистика", "Mentor: my stats btn"),
    # ── Start ──
    (
        "start.welcome",
        "<b>Привет, $name!</b>\n\nЯ буду напоминать вам о встречах и присылать полезную информацию.\nЧерез команду <b>/menu</b> можно открыть главное меню, посмотреть свои данные и доступные действия.\n\nЕсли что-то не работает — воспользуйся кнопкой Обратная связь / Баг.",
        "Welcome message",
    ),
    # ── Users ──
    ("user.btn.list", "Список пользователей", "Users: list btn"),
    ("user.btn.update", "Изменить пользователя", "Users: update btn"),
    ("user.btn.update_status", "🔄 Обновить статус", "Users: update status btn"),
    ("user.btn.update_role", "🛡 Обновить роль", "Users: update role btn"),
    ("user.btn.update_mentor", "👨‍🏫 Обновить ментора", "Users: update mentor btn"),
    (
        "user.btn.update_student_status",
        "🔄 Обновить статус менти",
        "Users: update student status btn",
    ),
    ("user.list.header", "<b>Список пользователей:</b>", "Users list header"),
    ("user.list.empty", "<b>Список пользователей пуст.</b>", "Users list empty"),
    ("user.update.what", "Что вы хотите обновить?", "Update user: choose param"),
    ("user.update.access_denied", "Доступ запрещен.", "Update user: access denied"),
    (
        "user.update.success",
        "Пользователь $name @$username\n$param обновлено на: $value",
        "Update user: success",
    ),
    # ── Cohorts ──
    ("cohort.btn.types", "Типы когорт", "Cohorts: types list btn"),
    ("cohort.btn.create_type", "Создать тип когорты", "Cohorts: create type btn"),
    ("cohort.types.header", "<b>Типы когорт:</b>", "Cohorts list header"),
    (
        "cohort.not_configured",
        "Notion не настроен (NOTION_TOKEN / NOTION_DATABASE_ID).",
        "Notion not configured",
    ),
    (
        "cohort.not_found",
        "Типы когорт не найдены в Notion.",
        "No cohort types found",
    ),
    # ── Mailings ──
    ("mailings.btn.list", "Список рассылок", "Mailings: list btn"),
    ("mailings.btn.add", "Добавить рассылку", "Mailings: add btn"),
    ("mailings.btn.delete", "Удалить рассылку", "Mailings: delete btn"),
    ("mailings.list.header", "<b>Список рассылок:</b>", "Mailings list header"),
    ("mailings.list.empty", "<b>Список рассылок пуст.</b>", "Mailings list empty"),
    ("mailings.choose_type", "Выберите тип рассылки:", "Choose mailing type"),
    ("mailings.enter_title", "Введите название рассылки:", "Enter mailing title"),
    # ── Meetings ──
    ("meeting.list.empty", "Список созвонов пуст.", "Meetings list empty"),
    ("meeting.list.header", "<b>Мои созвоны:</b>", "Meetings list header"),
    ("meeting.error.not_found", "Созвон не найден.", "Meeting not found"),
    (
        "meeting.error.no_access",
        "У вас нет доступа к этому созвону.",
        "Meeting: no access",
    ),
    (
        "meeting.error.already_completed",
        "Этот созвон уже завершён.",
        "Meeting already completed",
    ),
    (
        "meeting.error.active_exists",
        "У вас уже есть активный созвон. Сначала завершите его через кнопку или команду /end_call.",
        "Active call exists",
    ),
    # ── Mentor stats ──
    (
        "mentor_stats.header",
        "<b>Статистика ментора: $name</b>",
        "Mentor stats header",
    ),
    ("mentor_stats.no_scores", "Оценок пока нет.", "No scores yet"),
    ("mentor_stats.not_found", "Ментор не найден.", "Mentor not found"),
    (
        "mentor_stats.select",
        "Выберите ментора для просмотра статистики:",
        "Select mentor",
    ),
    ("mentor_stats.no_mentors", "Менторов не найдено.", "No mentors found"),
    # ── Triggers ──
    ("trigger.btn.create", "Создать правило", "Triggers: create btn"),
    ("trigger.btn.list", "Список правил", "Triggers: list btn"),
    ("trigger.btn.manual_send", "Отправить вручную", "Triggers: manual send btn"),
    ("trigger.menu.title", "Управление триггерами", "Triggers menu title"),
    ("trigger.no_rules", "Нет правил", "No trigger rules"),
    ("trigger.list.header", "Правила:", "Trigger rules header"),
    ("trigger.rule_not_found", "Правило не найдено", "Trigger rule not found"),
    ("trigger.deleted", "Правило удалено", "Trigger rule deleted"),
    # ── Trigger labels ──
    (
        "trigger.type.meeting_created",
        "Создание встречи",
        "Trigger type: meeting created",
    ),
    ("trigger.type.call_ended", "Завершение созвона", "Trigger type: call ended"),
    ("trigger.type.periodic_cron", "По расписанию", "Trigger type: periodic cron"),
    (
        "trigger.type.user_state_changed",
        "Смена статуса",
        "Trigger type: user state changed",
    ),
    ("trigger.type.manual", "Ручной", "Trigger type: manual"),
    (
        "trigger.action.send_notification",
        "Отправить уведомление",
        "Action: send notification",
    ),
    ("trigger.action.send_survey", "Отправить опрос", "Action: send survey"),
    (
        "trigger.recipient.event_student",
        "Менти из события",
        "Recipient: event student",
    ),
    (
        "trigger.recipient.event_mentor",
        "Ментор из события",
        "Recipient: event mentor",
    ),
    ("trigger.recipient.by_role", "По роли", "Recipient: by role"),
    ("trigger.recipient.by_cohort", "По когорте", "Recipient: by cohort"),
    ("trigger.recipient.by_state", "По статусу", "Recipient: by state"),
    (
        "trigger.recipient.specific_users",
        "Конкретные пользователи",
        "Recipient: specific users",
    ),
    # ── Surveys ──
    ("survey.btn.create", "Создать опрос", "Surveys: create btn"),
    ("survey.btn.list", "Список опросов", "Surveys: list btn"),
    ("survey.btn.results", "Результаты", "Surveys: results btn"),
    ("survey.menu.title", "Конструктор опросов", "Surveys menu title"),
    ("survey.no_surveys", "Нет созданных опросов", "No surveys"),
    ("survey.not_found", "Опрос не найден", "Survey not found"),
    ("survey.deleted", "Опрос удалён", "Survey deleted"),
    ("survey.type.text", "Текст", "Question type: text"),
    ("survey.type.rating", "Рейтинг (число)", "Question type: rating"),
    (
        "survey.type.single_choice",
        "Одиночный выбор",
        "Question type: single choice",
    ),
    (
        "survey.type.multiple_choice",
        "Множественный выбор",
        "Question type: multiple choice",
    ),
    # ── Dynamic surveys ──
    ("dynamic_survey.not_found", "Опрос не найден", "Dynamic survey not found"),
    (
        "dynamic_survey.already_completed",
        "Вы уже заполнили этот опрос",
        "Survey already completed",
    ),
    ("dynamic_survey.cancelled", "Опрос отменён.", "Survey cancelled"),
    # ── RBAC ──
    ("rbac.btn.create_role", "➕ Создать роль", "RBAC: create role btn"),
    ("rbac.btn.back_to_roles", "⬅️ К списку ролей", "RBAC: back to roles btn"),
    (
        "rbac.btn.manage_perms",
        "🔑 Управление пермишенами",
        "RBAC: manage perms btn",
    ),
    ("rbac.btn.delete_role", "🗑 Удалить роль", "RBAC: delete role btn"),
    ("rbac.menu.title", "<b>Управление ролями</b>", "RBAC menu title"),
    ("rbac.role_not_found", "Роль не найдена.", "Role not found"),
    ("rbac.confirm_delete", "Удалить роль <b>{name}</b>?", "Confirm role deletion"),
    (
        "rbac.users_cannot_delete",
        "Нельзя удалить роль, к которой привязаны пользователи.",
        "Cannot delete role with users",
    ),
    # ── Lead menu ──
    (
        "menu.btn.direction_students",
        "🎯 Менти направления",
        "Menu button: direction students",
    ),
    (
        "menu.btn.job_search_reports",
        "💼 Отчёты: поиск работы",
        "Menu button: job search reports",
    ),
    (
        "menu.btn.education_feedback",
        "📚 Обратная связь: сопровождение",
        "Menu button: education feedback",
    ),
    # ── Direction view ──
    (
        "direction.no_directions",
        "У вас нет назначенных направлений.",
        "Direction view: no directions assigned to lead",
    ),
    # ── Job search reports ──
    (
        "job_search.title",
        "💼 Отчёты по поиску работы",
        "Job search report: title",
    ),
    (
        "job_search.no_data",
        "Нет данных за выбранный период.",
        "Job search report: no data",
    ),
    (
        "job_search.choose_period",
        "Выберите период:",
        "Job search report: choose period",
    ),
    # ── Education feedback ──
    (
        "education.title",
        "📚 Обратная связь о сопровождении",
        "Education feedback: title",
    ),
    (
        "education.no_data",
        "Нет данных за выбранный период.",
        "Education feedback: no data",
    ),
    (
        "education.choose_period",
        "Выберите период:",
        "Education feedback: choose period",
    ),
    # ── Feedback report ──
    (
        "menu.btn.feedback_report",
        "📮 Обратная связь / Баг",
        "Menu button: feedback report",
    ),
    ("feedback.choose_type", "Выберите тип обращения:", "Feedback: choose type"),
    ("feedback.enter_text", "Введите текст обращения:", "Feedback: enter text"),
    (
        "feedback.choose_recipient",
        "Кому направить обращение?",
        "Feedback: choose recipient",
    ),
    (
        "feedback.attach_photo",
        "Прикрепите фото или нажмите «Пропустить»:",
        "Feedback: attach photo",
    ),
    ("feedback.sent", "✅ Ваше обращение отправлено.", "Feedback: sent confirmation"),
    (
        "feedback.bug_sent",
        "✅ Баг-репорт отправлен.",
        "Feedback: bug sent confirmation",
    ),
    # ── Lead sources ──
    (
        "menu.btn.referral_link",
        "🔗 Моя реферальная ссылка",
        "Menu button: referral link",
    ),
    (
        "menu.btn.channel_links",
        "📢 Канальные ссылки",
        "Menu button: channel links",
    ),
    (
        "start.welcome_referral",
        "<b>Привет, $name!</b>\n\nВас пригласил(а) <b>$referrer_name</b>.\n\nЯ буду напоминать вам о встречах и присылать полезную информацию.\nЧерез команду <b>/menu</b> можно открыть главное меню.",
        "Welcome message for referral deep link",
    ),
    (
        "start.welcome_channel",
        "<b>Привет, $name!</b>\n\nРады, что вы нашли нас!\n\nЯ буду напоминать вам о встречах и присылать полезную информацию.\nЧерез команду <b>/menu</b> можно открыть главное меню.",
        "Welcome message for channel deep link",
    ),
    (
        "lead_source.my_link",
        "🔗 <b>Ваша реферальная ссылка:</b>\n\n<code>$link</code>\n\nПриглашено пользователей: <b>$count</b>",
        "Referral link display with counter",
    ),
    (
        "lead_source.channel_list_title",
        "📢 <b>Канальные ссылки:</b>",
        "Channel links list title",
    ),
    (
        "lead_source.channel_created",
        "✅ Ссылка создана:\n\n<code>$link</code>\n\nОписание: $label",
        "Channel link created confirmation",
    ),
    (
        "lead_source.enter_label",
        "Введите описание для канальной ссылки (например, название поста):",
        "Prompt for channel link label",
    ),
    # ── Common ──
    ("common.cancel", "❌ Отмена", "Cancel button"),
    ("common.confirm.yes", "✅ Да, удалить", "Confirm: yes"),
    ("common.confirm.no", "❌ Отмена", "Confirm: no"),
    ("common.loading", "⏳ Загрузка...", "Loading indicator"),
]


# ── Helpers ─────────────────────────────────────────────────────────────


def _get_template_id(conn, slug: str) -> int:
    return conn.execute(
        sa.text("SELECT id FROM surveys.survey_templates WHERE slug = :s"),
        {"s": slug},
    ).scalar_one()


def _insert_rule(conn, rule: dict) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO triggers.trigger_rules "
            "(name, trigger_type, action_type, is_active, "
            " cron_expression, regularity, time_of_day, "
            " delay_seconds, delay_mode, "
            " recipient_type, recipient_config, action_config, trigger_config) "
            "SELECT "
            " :name, :trigger_type, :action_type, :is_active, "
            " :cron_expression, CAST(:regularity AS trigger_regularity_enum), :time_of_day, "
            " :delay_seconds, :delay_mode, "
            " :recipient_type, CAST(:recipient_config AS jsonb), CAST(:action_config AS jsonb), CAST(:trigger_config AS jsonb) "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM triggers.trigger_rules WHERE name = :name"
            ")"
        ),
        {
            "name": rule["name"],
            "trigger_type": rule["trigger_type"],
            "action_type": rule["action_type"],
            "is_active": rule.get("is_active", True),
            "cron_expression": rule.get("cron_expression"),
            "regularity": rule.get("regularity"),
            "time_of_day": str(rule["time_of_day"])
            if rule.get("time_of_day")
            else None,
            "delay_seconds": rule.get("delay_seconds", 0),
            "delay_mode": rule.get("delay_mode", "after_trigger"),
            "recipient_type": rule["recipient_type"],
            "recipient_config": json.dumps(rule["recipient_config"])
            if rule.get("recipient_config")
            else None,
            "action_config": json.dumps(rule["action_config"]),
            "trigger_config": json.dumps(rule["trigger_config"])
            if rule.get("trigger_config")
            else None,
        },
    )


# ── upgrade / downgrade ────────────────────────────────────────────────


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Permissions ──────────────────────────────────────────────────
    for codename, description in PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO iam.permissions (codename, description) "
                "VALUES (:codename, :description) "
                "ON CONFLICT (codename) DO NOTHING"
            ),
            {"codename": codename, "description": description},
        )

    # ── 2. Roles ────────────────────────────────────────────────────────
    for role in ROLES:
        conn.execute(
            sa.text(
                "INSERT INTO iam.roles (name, display_name) "
                "VALUES (:name, :display_name) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            role,
        )

    # ── 3. Role → Permission mappings ───────────────────────────────────
    for role_name, perm_codenames in ROLE_PERMISSIONS_MAP.items():
        role_id = conn.execute(
            sa.text("SELECT id FROM iam.roles WHERE name = :n"), {"n": role_name}
        ).scalar_one()
        for codename in perm_codenames:
            perm_id = conn.execute(
                sa.text("SELECT id FROM iam.permissions WHERE codename = :c"),
                {"c": codename},
            ).scalar_one()
            conn.execute(
                sa.text(
                    "INSERT INTO iam.role_permissions (role_id, permission_id) "
                    "VALUES (:rid, :pid) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"rid": role_id, "pid": perm_id},
            )

    # ── 4. Survey templates, questions, options ─────────────────────────
    for tmpl in TEMPLATES:
        conn.execute(
            sa.text(
                "INSERT INTO surveys.survey_templates (title, slug, description, is_active) "
                "VALUES (:title, :slug, :description, true) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {
                "title": tmpl["title"],
                "slug": tmpl["slug"],
                "description": tmpl["description"],
            },
        )

        tid = _get_template_id(conn, tmpl["slug"])

        for q in tmpl["questions"]:
            conn.execute(
                sa.text(
                    "INSERT INTO surveys.survey_questions "
                    "(template_id, sort_order, title, question_type, is_required, config) "
                    "VALUES (:tid, :sort_order, :title, :qtype, :is_required, CAST(:config AS jsonb)) "
                    "ON CONFLICT ON CONSTRAINT uq_survey_question_order DO NOTHING"
                ),
                {
                    "tid": tid,
                    "sort_order": q["sort_order"],
                    "title": q["title"],
                    "qtype": q["question_type"],
                    "is_required": q["is_required"],
                    "config": json.dumps(q["config"]) if q["config"] else None,
                },
            )

            if q["options"]:
                qid = conn.execute(
                    sa.text(
                        "SELECT id FROM surveys.survey_questions "
                        "WHERE template_id = :tid AND sort_order = :so"
                    ),
                    {"tid": tid, "so": q["sort_order"]},
                ).scalar_one()

                for i, opt in enumerate(q["options"]):
                    conn.execute(
                        sa.text(
                            "INSERT INTO surveys.survey_question_options "
                            "(question_id, sort_order, value, label) "
                            "VALUES (:qid, :so, :val, :lbl) "
                            "ON CONFLICT ON CONSTRAINT uq_survey_option_order DO NOTHING"
                        ),
                        {
                            "qid": qid,
                            "so": i + 1,
                            "val": opt["value"],
                            "lbl": opt["label"],
                        },
                    )

    # ── 5. Trigger rules ────────────────────────────────────────────────
    template_ids = {
        tmpl["slug"]: _get_template_id(conn, tmpl["slug"]) for tmpl in TEMPLATES
    }

    seed_rules = [
        {
            "name": "Уведомление о созвоне",
            "trigger_type": "meeting_created",
            "action_type": "send_notification",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "action_config": {"text": NOTIFY_TEXT},
        },
        {
            "name": "Напоминание за 5 минут",
            "trigger_type": "meeting_created",
            "action_type": "send_notification",
            "delay_seconds": 300,
            "delay_mode": "before_scheduled",
            "recipient_type": "event_student",
            "action_config": {"text": REMINDER_TEXT},
        },
        {
            "name": "Опрос менти после созвона",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "action_config": {
                "survey_template_id": template_ids["post_call_student"],
                "survey_title": "Опрос менти после созвона",
            },
        },
        {
            "name": "Фидбек ментора после созвона",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_mentor",
            "action_config": {
                "survey_template_id": template_ids["mentor_feedback"],
                "survey_title": "Фидбек ментора после созвона",
            },
        },
        {
            "name": "Двухнедельный опрос ментора",
            "trigger_type": "periodic_cron",
            "action_type": "send_survey",
            "regularity": "fortnight",
            "time_of_day": time(12, 0),
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "by_role",
            "recipient_config": {"role_name": "mentor"},
            "action_config": {
                "survey_template_id": template_ids["mentor_self_review"],
                "survey_title": "Двухнедельный опрос ментора",
            },
        },
        {
            "name": "Опрос менти после первого созвона (greeting)",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "delay_seconds": 86400,
            "delay_mode": "after_trigger",
            "recipient_type": "event_student",
            "trigger_config": {"is_first_call": True, "student_stage": "greeting"},
            "action_config": {
                "survey_template_id": template_ids["greeting_mentee_feedback"],
                "survey_title": "Опрос менти после первого созвона",
            },
        },
        {
            "name": "Опрос ментора после первого созвона (greeting)",
            "trigger_type": "call_ended",
            "action_type": "send_survey",
            "delay_seconds": 86400,
            "delay_mode": "after_trigger",
            "recipient_type": "event_mentor",
            "trigger_config": {"is_first_call": True, "student_stage": "greeting"},
            "action_config": {
                "survey_template_id": template_ids["greeting_mentor_feedback"],
                "survey_title": "Опрос ментора после первого созвона",
            },
        },
        {
            "name": "Еженедельный опрос менти (Study)",
            "trigger_type": "periodic_cron",
            "action_type": "send_survey",
            "cron_expression": "0 12 * * 1",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "by_state",
            "recipient_config": {"state": "Study"},
            "action_config": {
                "survey_template_id": template_ids["weekly_mentee_study"],
                "survey_title": "Еженедельный опрос",
            },
        },
        {
            "name": "Еженедельный опрос менти (Search)",
            "trigger_type": "periodic_cron",
            "action_type": "send_survey",
            "cron_expression": "0 12 * * 1",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "by_state",
            "recipient_config": {"state": "search"},
            "action_config": {
                "survey_template_id": template_ids["weekly_mentee_search"],
                "survey_title": "Еженедельный опрос (Search)",
            },
        },
        {
            "name": "Двухнедельный опрос менти (Search)",
            "trigger_type": "periodic_cron",
            "action_type": "send_survey",
            "regularity": "fortnight",
            "time_of_day": time(12, 0),
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "by_state",
            "recipient_config": {"state": "search"},
            "action_config": {
                "survey_template_id": template_ids["search_mentee_biweekly"],
                "survey_title": "Опрос по поиску работы",
            },
        },
        {
            "name": "Lead→Study: Welcome",
            "trigger_type": "cohort_changed",
            "action_type": "send_notification",
            "delay_seconds": 0,
            "delay_mode": "after_trigger",
            "recipient_type": "event_user",
            "action_config": {"text": LEAD_TO_STUDY_TEXT},
            "trigger_config": {
                "cohort_type": "Status",
                "from_value": "Lead",
                "to_value": "Study",
            },
        },
    ]
    for rule in seed_rules:
        _insert_rule(conn, rule)

    # ── 6. UI texts ─────────────────────────────────────────────────────
    for key, value, description in UI_TEXTS:
        conn.execute(
            sa.text(
                "INSERT INTO public.ui_texts (key, value, description) "
                "VALUES (:key, :value, :description) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"key": key, "value": value, "description": description},
        )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("DELETE FROM public.ui_texts"))
    conn.execute(sa.text("DELETE FROM triggers.trigger_rules"))
    conn.execute(sa.text("DELETE FROM surveys.survey_question_options"))
    conn.execute(sa.text("DELETE FROM surveys.survey_questions"))
    conn.execute(sa.text("DELETE FROM surveys.survey_templates"))
    conn.execute(sa.text("DELETE FROM iam.role_permissions"))
    conn.execute(sa.text("DELETE FROM iam.roles"))
    conn.execute(sa.text("DELETE FROM iam.permissions"))
