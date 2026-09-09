"""Domain vocabulary shared by the engine, the models and the forms.

Each member's ``value`` is the string stored in the database and sent by the
forms. Translated labels for the UI live next to the forms and templates, not
here, so this module stays free of Flask. ``StrEnum`` members compare equal to
their string value, which keeps engine code readable (``sex == "male"``).
"""

from __future__ import annotations

from enum import StrEnum


class Sex(StrEnum):
    """Biological sex, needed by the metabolic formulas (not gender identity)."""

    MALE = "male"
    FEMALE = "female"


class BodyFatMethod(StrEnum):
    """How a body-fat percentage was obtained; drives the confidence level."""

    NONE = "none"
    NAVY = "navy"
    SCALE = "scale"
    CALIPERS = "calipers"
    DEXA = "dexa"
    VISUAL = "visual"


class JobActivity(StrEnum):
    """Occupational activity, used to estimate NEAT when steps are unknown."""

    SEDENTARY = "sedentary"
    STANDING = "standing"
    LIGHT_PHYSICAL = "light_physical"
    HEAVY_PHYSICAL = "heavy_physical"


class ActivityIntensity(StrEnum):
    """Intensity of sport practised outside the gym (maps to MET ranges)."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class TrainingExperience(StrEnum):
    """Resistance-training history."""

    NONE = "none"
    UNDER_6_MONTHS = "under_6_months"
    MONTHS_6_TO_24 = "6_to_24_months"
    YEARS_2_TO_5 = "2_to_5_years"
    OVER_5_YEARS = "over_5_years"


class TrainingLocation(StrEnum):
    """Where the person trains; narrows the default equipment list."""

    FULL_GYM = "full_gym"
    BASIC_GYM = "basic_gym"
    HOME_EQUIPMENT = "home_equipment"
    HOME_BODYWEIGHT = "home_bodyweight"


class Goal(StrEnum):
    """Primary goal chosen in the questionnaire."""

    FAT_LOSS = "fat_loss"
    RECOMPOSITION = "recomposition"
    MUSCLE_GAIN = "muscle_gain"
    MAINTENANCE = "maintenance"
    PERFORMANCE = "performance"


class Aggressiveness(StrEnum):
    """Requested pace; safety limits always override it."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class DietPattern(StrEnum):
    """Dietary pattern that constrains food suggestions."""

    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    PESCETARIAN = "pescetarian"
    HALAL = "halal"
    KOSHER = "kosher"


class Level(StrEnum):
    """Generic three-step scale (budget, cooking time...)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InjuryArea(StrEnum):
    """Body areas the questionnaire can flag as injured or limited."""

    SHOULDER = "shoulder"
    ELBOW = "elbow"
    WRIST = "wrist"
    NECK = "neck"
    LOWER_BACK = "lower_back"
    HIP = "hip"
    KNEE = "knee"
    ANKLE = "ankle"


class Severity(StrEnum):
    """Severity of an injury or limitation."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class MuscleGroup(StrEnum):
    """Muscle groups used for volume accounting and priorities."""

    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    ABS = "abs"
    LOWER_BACK = "lower_back"
    TRAPS = "traps"
    ADDUCTORS = "adductors"


class MovementPattern(StrEnum):
    """Movement pattern an exercise covers; routines must cover them all."""

    HORIZONTAL_PUSH = "horizontal_push"
    VERTICAL_PUSH = "vertical_push"
    HORIZONTAL_PULL = "horizontal_pull"
    VERTICAL_PULL = "vertical_pull"
    KNEE_DOMINANT = "knee_dominant"
    HIP_DOMINANT = "hip_dominant"
    CORE = "core"
    ISOLATION = "isolation"


class Mechanic(StrEnum):
    """Compound (multi-joint) or isolation (single-joint)."""

    COMPOUND = "compound"
    ISOLATION = "isolation"


class Force(StrEnum):
    """Direction of force, used for the push/pull balance."""

    PUSH = "push"
    PULL = "pull"
    STATIC = "static"


class TechnicalLevel(StrEnum):
    """Technical skill an exercise demands."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class EquipmentCategory(StrEnum):
    """Coarse grouping of equipment for the questionnaire."""

    FREE_WEIGHTS = "free_weights"
    MACHINES = "machines"
    CABLES = "cables"
    BODYWEIGHT = "bodyweight"
    ACCESSORIES = "accessories"


class PlanStatus(StrEnum):
    """Lifecycle of a nutrition plan or a routine."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class Confidence(StrEnum):
    """How much to trust an estimate (shown in the UI)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BmrMethod(StrEnum):
    """Formula selected for the basal metabolic rate."""

    KATCH_MCARDLE = "katch_mcardle"
    MIFFLIN_ST_JEOR = "mifflin_st_jeor"
    HARRIS_BENEDICT = "harris_benedict"


class SplitType(StrEnum):
    """Training split families."""

    FULL_BODY = "full_body"
    UPPER_LOWER = "upper_lower"
    PUSH_PULL_LEGS = "push_pull_legs"
    UPPER_LOWER_PPL = "upper_lower_ppl"
    ARNOLD = "arnold"
    PPL_TWICE = "ppl_twice"


class MealTiming(StrEnum):
    """Position of a meal relative to training."""

    REGULAR = "regular"
    PRE_WORKOUT = "pre_workout"
    POST_WORKOUT = "post_workout"


class AdjustmentReason(StrEnum):
    """Why a plan was (re)calculated."""

    INITIAL = "initial"
    SCHEDULED_REVIEW = "scheduled_review"
    USER_REQUEST = "user_request"
    PROFILE_CHANGE = "profile_change"
    LOSS_TOO_FAST = "loss_too_fast"
    LOSS_TOO_SLOW = "loss_too_slow"
    GAIN_TOO_FAST = "gain_too_fast"
    GAIN_TOO_SLOW = "gain_too_slow"
    PLATEAU = "plateau"
    DIET_BREAK = "diet_break"
    REFEED = "refeed"
    SAFETY_LIMIT = "safety_limit"


class WorkoutStatus(StrEnum):
    """State of a logged training session."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SetType(StrEnum):
    """Warm-up sets are logged but do not count as effective volume."""

    WARMUP = "warmup"
    WORKING = "working"


class CardioKind(StrEnum):
    """Cardio modality logged or prescribed."""

    LISS = "liss"
    HIIT = "hiit"
    STEPS = "steps"
