# AIR user options audit — Days 1–30

`Other` means that the shared **Другое → custom textarea** control is enabled. `Fixed` means that the question is deliberately constrained because it is a technical checkpoint. Day 29 already uses direct free-text fields, so a second “Other” control would be redundant. “Plan” is enabled only for executable action-like semantics; reason, motivation and reflection never become plan steps. “SOS” means that the value participates in reason/action/motivation personalization.

| Day | Question / field | Current UI type | Other | Semantic response type | Personal Plan | SOS personalization |
|---:|---|---|---|---|---|---|
| 1 | `quit_reasons` | multi | Yes | motivation | No | Motivation |
| 1 | `primary_quit_reason` | single | Yes | motivation | No | Motivation |
| 1 | `user_triggers` | multi | Yes | trigger | No | Reasons |
| 1 | `primary_triggers` | multi | Yes | trigger | No | Reasons |
| 1 | `nicotine_beliefs` | multi | Yes | reason | No | Reasons |
| 1 | `quit_concerns` | multi | Yes | reason | No | Reasons |
| 2 | `personal_habit_loop.trigger` | builder | Yes | trigger | No | Reasons |
| 2 | `personal_habit_loop.first_signal` | builder | Yes | reason | No | Reasons |
| 2 | `personal_habit_loop.expected` | builder | Yes | reason | No | Reasons |
| 2 | `personal_habit_loop.alternative` | builder | Yes | coping_action | Yes | Actions |
| 3 | `usual_high_desire_response` | single | Yes | reflection | No | No |
| 3 | `pause_plan` | action | Yes | coping_action | Yes | Actions |
| 4 | `noticed_changes` | multi | Yes | reason | No | Reasons |
| 4 | `main_change` | priority | Yes | reason | No | Reasons |
| 4 | `change_response` | action | Yes | coping_action | Yes | Actions |
| 5 | `trigger_plan.first_action` | builder | Yes | plan_action | Yes | Actions |
| 5 | `trigger_plan.backup_action` | builder | Yes | plan_action | Yes | Actions |
| 5 | `trigger_plan.sos_threshold` | builder | Fixed | general | No | No |
| 6 | `automatic_trigger` | priority | Yes | trigger | No | Reasons |
| 6 | `changed_routine` | action | Yes | coping_action | Yes | Actions |
| 7 | `week_one_challenge` | priority | Yes | reason | No | Reasons |
| 7 | `week_one_help` | priority | Yes | coping_action | Yes | Actions |
| 8 | `relaxation_breakdown.before` | builder | Yes | reason | No | Reasons |
| 8 | `relaxation_breakdown.after` | builder | Yes | reflection | No | No |
| 8 | `relaxation_breakdown.replacement` | builder | Yes | replacement | Yes | Actions |
| 9 | `focus_context` | priority | Yes | reason | No | Reasons |
| 9 | `focus_experiment_start` | single | Fixed | general | No | No |
| 9 | `focus_experiment` | single | Yes | reflection | No | No |
| 10 | `pleasure_components` | multi | Yes | reason | No | Reasons |
| 10 | `pleasure_replacement` | priority | Yes | replacement | Yes | Actions |
| 11 | `break_replacement` | ordered | Yes | replacement | Yes | Actions |
| 12 | `boredom_menu.one_minute` | builder | Yes | coping_action | Yes | Actions |
| 12 | `boredom_menu.three_minutes` | builder | Yes | coping_action | Yes | Actions |
| 12 | `boredom_menu.ten_minutes` | builder | Yes | coping_action | Yes | Actions |
| 13 | `evening_ritual` | ordered | Yes | plan_action | Yes | Actions |
| 14 | `belief_less_convincing` | priority | Yes | reflection | No | No |
| 15 | `stress_plan.first_action` | builder | Yes | plan_action | Yes | Actions |
| 15 | `stress_plan.backup_action` | builder | Yes | plan_action | Yes | Actions |
| 15 | `stress_plan.sos_threshold` | builder | Fixed | general | No | No |
| 16 | `emotion_need_action.emotion` | builder | Yes | reason | No | Reasons |
| 16 | `emotion_need_action.need` | builder | Yes | reason | No | Reasons |
| 16 | `emotion_need_action.action` | builder | Yes | coping_action | Yes | Actions |
| 17 | `social_first_reply` | scenario | Yes | social_response | Yes | Actions |
| 17 | `social_second_reply` | scenario | Yes | social_response | Yes | Actions |
| 18 | `evening_plan.risk` | builder | Yes | reason | No | Reasons |
| 18 | `evening_plan.offer_response` | builder | Yes | social_response | Yes | Actions |
| 18 | `evening_plan.sos_threshold` | builder | Fixed | general | No | No |
| 18 | `evening_plan.exit` | builder | Yes | coping_action | Yes | Actions |
| 19 | `after_meal_plan.usual` | builder | Yes | reason | No | Reasons |
| 19 | `after_meal_plan.new_action` | builder | Yes | plan_action | Yes | Actions |
| 20 | `movement_switch` | action | Yes | coping_action | Yes | Actions |
| 20 | `movement_try_now` | single | Fixed | general | No | No |
| 20 | `movement_effect` | single | Yes | reflection | No | No |
| 21 | No choice/custom question | — | — | — | — | — |
| 22 | `one_time_first` | scenario | Yes | plan_action | Yes | Actions |
| 22 | `one_time_risk_followup` | scenario | Yes | plan_action | Yes | Actions |
| 22 | `one_time_coping_followup` | scenario | Yes | plan_action | Yes | Actions |
| 23 | `post_lapse_thought` | scenario | Yes | reflection | No | No |
| 23 | `post_lapse_choice` | scenario | Yes | lapse_plan | Yes | Actions |
| 24 | `lapse_analysis.main_factor` | builder | Yes | reason | No | Reasons |
| 24 | `lapse_analysis.next_action` | builder | Yes | lapse_plan | Yes | Actions |
| 25 | `unexpected_feature` | priority | Yes | reflection | No | No |
| 25 | `unexpected_desire_response` | action | Yes | plan_action | Yes | Actions |
| 26 | `state_need_action.state` | builder | Yes | reason | No | Reasons |
| 26 | `state_need_action.need` | builder | Yes | reason | No | Reasons |
| 26 | `state_need_action.action` | builder | Yes | coping_action | Yes | Actions |
| 27 | `scenario_decision_one` | scenario | Yes | plan_action | Yes | Actions |
| 27 | `scenario_decision_two` | scenario | Yes | social_response | Yes | Actions |
| 27 | `scenario_decision_three` | scenario | Yes | plan_action | Yes | Actions |
| 28 | `warning_signs` | multi | Yes | reason | No | Reasons |
| 28 | `warning_priority` | priority | Yes | reason | No | Reasons |
| 28 | `warning_response` | action | Yes | plan_action | Yes | Actions |
| 29 | `protection_plan.strong_desire` | free input | Built in | plan_action | Yes | Actions |
| 29 | `protection_plan.stress` | free input | Built in | plan_action | Yes | Actions |
| 29 | `protection_plan.social` | free input | Built in | social_response | Yes | Actions |
| 29 | `protection_plan.one_time` | free input | Built in | plan_action | Yes | Actions |
| 29 | `protection_plan.lapse` | free input | Built in | lapse_plan | Yes | Actions |
| 29 | `protection_replacement` | action | Yes | plan_action | Yes | Actions |
| 30 | `final_change` | multi | Yes | reflection | No | No |
| 30 | `keep_next` | multi | Yes | plan_action | Yes | Actions |
| 30 | `most_useful_strategy` | priority | Yes | coping_action | Yes | Actions |

Technical scales (including intensity 1–10), comparisons, dates, navigation, confirmations, analytics/checkpoints and result cards are intentionally outside the custom-response system.
