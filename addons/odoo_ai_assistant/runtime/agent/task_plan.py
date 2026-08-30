"""Visible provider-neutral TaskPlan contract with no execution authority."""

from __future__ import annotations

from dataclasses import dataclass

_ALLOWED_STATES = frozenset({"pending", "in_progress", "completed", "blocked", "skipped"})
_MAX_TASK_STEPS = 12


class TaskPlanError(RuntimeError):
    def __init__(self, code: str = "agent_task_plan_invalid") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TaskPlanStep:
    step_id: str
    title: str
    state: str = "pending"
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """High-level mutable-by-revision plan for user-visible progress only.

    A TaskPlan may describe investigation or resolution work, but it never names an execution
    authority and cannot be passed to CapabilityExecutor. Effects require a separate EffectPlan.
    """

    goal: str
    revision: int
    steps: tuple[TaskPlanStep, ...]

    def payload(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "revision": self.revision,
            "steps": [
                {
                    "step_id": step.step_id,
                    "title": step.title,
                    "state": step.state,
                    "depends_on": list(step.depends_on),
                }
                for step in self.steps
            ],
        }


def parse_task_plan(value: object) -> TaskPlan:
    if not isinstance(value, dict) or set(value) != {"goal", "revision", "steps"}:
        raise TaskPlanError()
    goal = value.get("goal")
    revision = value.get("revision")
    raw_steps = value.get("steps")
    if (
        not isinstance(goal, str)
        or not 1 <= len(goal.strip()) <= 1_000
        or "\x00" in goal
        or type(revision) is not int
        or revision < 1
        or not isinstance(raw_steps, list)
        or not 1 <= len(raw_steps) <= _MAX_TASK_STEPS
    ):
        raise TaskPlanError()
    steps: list[TaskPlanStep] = []
    known: set[str] = set()
    for raw in raw_steps:
        if not isinstance(raw, dict) or set(raw) != {
            "step_id",
            "title",
            "state",
            "depends_on",
        }:
            raise TaskPlanError()
        step_id = raw.get("step_id")
        title = raw.get("title")
        state = raw.get("state")
        depends_on = raw.get("depends_on")
        if (
            not isinstance(step_id, str)
            or not 1 <= len(step_id) <= 128
            or step_id in known
            or not isinstance(title, str)
            or not 1 <= len(title.strip()) <= 512
            or "\x00" in title
            or state not in _ALLOWED_STATES
            or not isinstance(depends_on, list)
            or any(not isinstance(item, str) or item not in known for item in depends_on)
            or len(set(depends_on)) != len(depends_on)
        ):
            raise TaskPlanError()
        steps.append(
            TaskPlanStep(
                step_id=step_id,
                title=" ".join(title.split()),
                state=state,
                depends_on=tuple(depends_on),
            )
        )
        known.add(step_id)
    return TaskPlan(goal=" ".join(goal.split()), revision=revision, steps=tuple(steps))
