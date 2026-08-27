export type AccessLinks = { support: string | null; terms: string | null; privacy: string | null };

export type Access = {
  status: "free" | "active" | "expired";
  plan: string;
  ends_at: string | null;
  development_activation_available: boolean;
  links: AccessLinks;
};

export type Recovery = { hours: number; title: string; description: string; reached: boolean };
export type Dashboard = {
  first_name: string;
  quit_started_at: string | null;
  elapsed_seconds: number;
  days: number;
  hours: number;
  money_saved: number;
  units_avoided: number;
  unit_label: string;
  program_day: number;
  program_length: number;
  recovery: Recovery;
  today_task: { day: number; title: string; description: string };
  program_started: boolean;
  has_active_attempt: boolean;
  number_of_attempts: number;
};
export type ProgramDay = { number: number; title: string; description: string; task: string; status: string; completed: boolean; interactive: boolean; dev_preview_available: boolean; dev_unlocked: boolean };
export type Program = { current_day: number; total_days: number; program_started: boolean; is_program_dev: boolean; completed_count: number; personal_plan_strategy_count: number; days: ProgramDay[] };
export type StepOption = { id: string; label: string; response_id?: number; personalized_reason?: string };
export type RememberedResponse = { id: number; value: string; response_type: string; context_id: string | null; parent_response_id: number | null; focus: string | null; usage_count: number; average_effect: number | null };
export type StructuredStepValue = Record<string, string>;
export type ProgramStep = {
  id: string;
  type: "start" | "info" | "theory" | "single_select" | "multi_select" | "priority_select" | "action_picker" | "ordered_select" | "plan_builder" | "comparison" | "scenario_choice" | "result_card" | "scale" | "text" | "structured_input" | "personalized_cards" | "personalized_summary" | "personalized_insight" | "selected_insights" | "checkpoint" | "task" | "completion";
  title: string;
  body: string;
  required: boolean;
  max_selections: number | null;
  button_text: string;
  options: StepOption[];
  value: string | string[] | number | StructuredStepValue | null;
  content: {
    highlight?: string;
    placeholder?: string;
    source_step?: string;
    fields?: { id: string; label: string; placeholder?: string; response_type?: string; response_context?: string | null }[];
    reactions?: Record<string, string>;
    response_type?: string;
    allow_other?: boolean;
    other_placeholder?: string;
    response_context?: string | null;
    remembered_options?: { id: number; value: string }[];
  };
  cards?: { id: string; title: string; short_explanation?: string; why_it_happens?: string; first_tip?: string }[];
  summary?: { primary_reason: string | null; primary_triggers: string[]; beliefs: string[]; concerns: string[] };
  insight?: { title: string; body: string; is_fallback: boolean; plan_items?: PersonalPlanItem[] };
  insights?: { id: string; text: string }[];
  analytics?: { label: string; value: string; note: string }[];
  builder_fields?: { id: string; label: string; options: StepOption[]; exclude_answer?: string | null; response_type?: string; allow_other?: boolean; other_placeholder?: string; response_context?: string | null; remembered_options?: { id: number; value: string }[] }[];
  comparison?: { items: StepOption[]; scale: StepOption[] };
  result?: { title: string; style: string; items: { label: string; value: string; raw: unknown }[] };
};
export type ProgramDayDetail = {
  number: number; title: string; short_description: string; achievement: string | null;
  task_title: string | null; task_description: string | null; task_progress: number;
  current_step: string; step_index: number; total_steps: number; completed: boolean; step: ProgramStep;
  evidence_category: string;
  dev_preview: boolean;
};
export type Progress = Dashboard & {
  completed_program_days: number;
  recovery_timeline: Recovery[];
  achievements: { id: string; title: string; unlocked: boolean }[];
  current_streak_seconds: number;
  best_streak_seconds: number;
  total_nicotine_free_seconds: number;
  number_of_attempts: number;
};
export type SupportContext = {
  triggers: StepOption[];
  primary_triggers: string[];
  emotions: StepOption[];
  primary_quit_reason: string | null;
  primary_quit_reason_label: string | null;
  motivation_text: string;
  has_personal_motivation: boolean;
  motivation_stats: { elapsed_seconds: number; money_saved: number; cravings_survived: number };
  game_best_height: number;
  personal_plan: PersonalPlan;
  recommendations: Record<string, { action_id: string; label: string; support_type: "breathing" | "change_activity" | "replacement_action" | "motivation" | "ai_support"; reason: string }[]>;
  tool_analytics: {
    minimum_sample_size: number;
    usage_count: Record<string, number>;
    overall: Record<string, { sample_size: number; average_effect: number }>;
    by_trigger: Record<string, Record<string, { sample_size: number; average_effect: number }>>;
    best_overall_tool: string | null;
    best_tool_by_trigger: Record<string, string>;
  };
};
export type PersonalPlanItem = { category: string; category_label: string; title: string; reasons: string[]; steps: string[]; source_day: number; source_key: string; priority: number };
export type PersonalPlan = { items: PersonalPlanItem[]; by_category: Record<string, PersonalPlanItem>; history: PersonalPlanItem[]; strategy_count: number; has_plan: boolean };
export type Profile = {
  first_name: string;
  username: string | null;
  nicotine_type: string;
  daily_units: number;
  unit_label: string;
  quit_started_at: string | null;
  registered_at: string;
  access_status: string;
  plan: string;
  motivation: string | null;
  links: AccessLinks;
};
