RUBRIC_HINTS_BY_OBSERVANCE = {
    "AdventI": (
        "The Exhortation is traditionally read on the First Sunday of Advent.",
    ),
    "LentI": ("The Exhortation is traditionally read on the First Sunday in Lent.",),
    "TrinitySunday": (
        "The Exhortation is traditionally read on Trinity Sunday.",
        "The Athanasian Creed may be used on Trinity Sunday.",
    ),
}


def resolve_service_rubric_hints(observance_handle):
    if not observance_handle:
        return []
    return list(RUBRIC_HINTS_BY_OBSERVANCE.get(observance_handle, ()))
