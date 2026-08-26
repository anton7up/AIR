from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryMilestone:
    hours: int
    title: str
    description: str


# Neutral wellbeing copy; medical claims can later be supplied from reviewed content.
RECOVERY_MILESTONES: tuple[RecoveryMilestone, ...] = (
    RecoveryMilestone(1, "Первый час", "Ты уже начал новый этап. Сосредоточься на ближайшем небольшом шаге."),
    RecoveryMilestone(24, "Первые сутки", "Организм привыкает к изменению привычного ритма. Поддерживай себя водой и отдыхом."),
    RecoveryMilestone(72, "Три дня", "Организм продолжает адаптироваться к жизни без никотина."),
    RecoveryMilestone(168, "Первая неделя", "Новый распорядок становится знакомее. Продолжай замечать свои триггеры."),
    RecoveryMilestone(720, "Первый месяц", "Ты сформировал значимый опыт жизни без никотина."),
)
