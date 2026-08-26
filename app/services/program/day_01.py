from app.services.program.schema import ProgramDay, ProgramStep, StepOption

DAY_01 = ProgramDay(
    number=1,
    title="Зачем тебе никотин?",
    short_description="Находим твою личную точку старта.",
    achievement="🏆 Первый шаг",
    task_title="🎯 Поймай 3 момента",
    task_description="Перед эпизодом сильного желания остановись на 10 секунд и отметь его в AIR.",
    steps=(
        ProgramStep(
            "start",
            "start",
            "Зачем тебе никотин?",
            "Сегодня начинается твой путь в AIR. С этого момента мы начинаем считать время без никотина. Начнём с сегодняшнего дня.",
            button_text="Начать отказ",
        ),
        ProgramStep(
            "quit_reasons",
            "multi_select",
            "Почему ты решил отказаться от никотина?",
            required=True,
            options_source="quit_reasons",
        ),
        ProgramStep(
            "primary_quit_reason",
            "single_select",
            "А какая причина для тебя сейчас самая важная?",
            required=True,
            options_source="selected:quit_reasons",
        ),
        ProgramStep(
            "trigger_intro",
            "theory",
            "Что стоит знать о триггерах",
            """Желание никотина часто связано не только с самим веществом. Со временем употребление может стать частью повторяющихся ситуаций: утреннего кофе, дороги, перерыва, стресса, общения, окончания еды или скуки.

Когда два действия много раз происходят рядом, мозг начинает ожидать одно после другого. Поэтому знакомая ситуация иногда запускает желание ещё до того, как человек успевает об этом подумать. Такие ситуации удобно называть триггерами.

Цель AIR — не убрать из жизни кофе, друзей, работу или стресс. Мы будем постепенно отделять эти ситуации от автоматического употребления никотина. Сегодня важно не бороться со всеми триггерами сразу. Сначала нужно понять, какие из них работают именно у тебя. Это стартовая гипотеза, а не диагноз: следующие дни и реальные наблюдения помогут сделать карту точнее. Здесь нет правильного набора ответов — важен твой настоящий опыт.""",
            button_text="Найти мои триггеры",
            content={"highlight": "Сначала замечаем связь, затем постепенно меняем её."},
        ),
        ProgramStep(
            "user_triggers",
            "multi_select",
            "Когда тебе особенно хочется никотина?",
            required=True,
            options_source="triggers",
        ),
        ProgramStep(
            "primary_triggers",
            "multi_select",
            "Какие из этих ситуаций для тебя самые сложные?",
            "Выбери не больше трёх.",
            required=True,
            max_selections=3,
            options_source="selected:user_triggers",
        ),
        ProgramStep(
            "trigger_cards",
            "personalized_cards",
            "Твои основные ситуации",
            "Это не диагноз — только первые связи, с которыми мы будем работать.",
            options_source="cards:primary_triggers",
        ),
        ProgramStep(
            "nicotine_beliefs",
            "multi_select",
            "Что, по твоему ощущению, никотин тебе даёт?",
            required=True,
            options_source="beliefs",
        ),
        ProgramStep(
            "belief_ack",
            "info",
            "Запомнил",
            "Сейчас мы не будем спорить с этими ощущениями. В следующие дни отдельно разберём стресс, концентрацию, удовольствие и привычные ритуалы.",
        ),
        ProgramStep(
            "quit_concerns",
            "multi_select",
            "Что больше всего беспокоит тебя в отказе?",
            required=True,
            options_source="concerns",
        ),
        ProgramStep(
            "summary",
            "personalized_summary",
            "Твоя стартовая карта",
            "Это не диагноз и не окончательный вывод. Это стартовая точка AIR.",
        ),
        ProgramStep(
            "task",
            "task",
            "🎯 Поймай 3 момента",
            "Сегодня перед тремя эпизодами сильного желания остановись на 10 секунд и нажми «Отметить желание никотина».",
        ),
        ProgramStep(
            "completion",
            "completion",
            "День 1 завершён",
            "AIR уже знает твои основные причины, ситуации и опасения. Дальше программа будет использовать эту информацию.",
            options=(StepOption("achievement", "🏆 Первый шаг"),),
            button_text="Завершить День 1",
        ),
    ),
    evidence_category="trigger identification and self-monitoring",
    evidence_notes="Исходная карта причин, триггеров, убеждений и опасений для последующей персонализации.",
)
