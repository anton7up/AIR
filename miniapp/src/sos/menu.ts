import type { SupportType } from "./logic";

export const SOS_MENU_ITEMS: { id: SupportType; label: string; hint: string }[] = [
  { id: "breathing", label: "Успокоиться", hint: "Квадратное дыхание" },
  { id: "distraction", label: "Поиграть", hint: "Игра «Выше облаков»" },
  { id: "motivation", label: "Напомнить, зачем я бросаю", hint: "Вернуться к своей причине" },
  { id: "personal_plan", label: "Мой план", hint: "Твои сохранённые шаги" },
  { id: "replacement_action", label: "Занять рот / руки", hint: "Одно конкретное действие" },
  { id: "change_activity", label: "Переключиться", hint: "Сменить действие на 2 минуты" },
];
