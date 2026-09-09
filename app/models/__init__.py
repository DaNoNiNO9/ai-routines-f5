"""SQLAlchemy models. Importing this package registers every table on ``db.metadata``."""

from app.models.base import SoftDeleteMixin, TimestampMixin, UTCDateTime, utcnow
from app.models.exercise import Equipment, Exercise, ExerciseAlternative, exercise_equipment
from app.models.onboarding import QuestionnaireDraft
from app.models.plan import Meal, Plan, PlanAdjustment
from app.models.profile import Injury, Profile
from app.models.routine import Routine, RoutineDay, RoutineExercise
from app.models.tracking import ActivityLog, BodyMeasurement, IntakeLog, WeightLog
from app.models.user import User, user_equipment
from app.models.workout import SetLog, WorkoutSession

__all__ = [
    "ActivityLog",
    "BodyMeasurement",
    "Equipment",
    "Exercise",
    "ExerciseAlternative",
    "Injury",
    "IntakeLog",
    "Meal",
    "Plan",
    "PlanAdjustment",
    "Profile",
    "QuestionnaireDraft",
    "Routine",
    "RoutineDay",
    "RoutineExercise",
    "SetLog",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UTCDateTime",
    "User",
    "WeightLog",
    "WorkoutSession",
    "exercise_equipment",
    "user_equipment",
    "utcnow",
]
