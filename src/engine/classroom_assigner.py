"""Assign rooms and time slots to every exam in a generated schedule."""

import heapq
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from itertools import combinations

from src.domain.classroom import Classroom
from src.domain.classroom_assignment import ClassroomAssignment
from src.domain.course import Course
from src.domain.proctor import ProctorConfig
from src.domain.schedule import Schedule
from src.domain.time_slot import TimeSlot


# Feature 4 variant limits.
# None means there is no total classroom-variant limit.
# The UI/controller still request variants in pages, so Auto Variants can load
# them gradually without freezing while trying to compute everything at once.
MAX_CLASSROOM_OPTIONS_PER_DAY: int | None = None
MAX_CLASSROOM_OPTIONS_PER_SCHEDULE: int | None = None


def _balanced_distribution(
    rooms: list[Classroom],
    student_count: int,
) -> list[tuple[Classroom, int]] | None:
    """Split students as evenly as possible without exceeding room capacities."""
    selected: list[Classroom] = []
    total_capacity = 0

    for room in rooms:
        selected.append(room)
        total_capacity += room.capacity
        if total_capacity >= student_count:
            break

    if total_capacity < student_count:
        return None

    counts = [0] * len(selected)
    heap = [(0, index) for index in range(len(selected))]
    heapq.heapify(heap)

    for _ in range(student_count):
        while heap:
            count, index = heapq.heappop(heap)
            if count < selected[index].capacity:
                break
        else:
            return None

        counts[index] += 1
        heapq.heappush(heap, (counts[index], index))

    return list(zip(selected, counts))


def _balanced_distribution_for_selected_rooms(
    rooms: list[Classroom],
    student_count: int,
) -> list[tuple[Classroom, int]] | None:
    """Split students across exactly the given rooms.

    Unlike _balanced_distribution(), this helper does not pick a prefix of the
    available room list. It is used for variant generation after a candidate
    room combination has already been selected.
    """
    if sum(room.capacity for room in rooms) < student_count:
        return None

    counts = [0] * len(rooms)
    heap = [(0, index) for index in range(len(rooms))]
    heapq.heapify(heap)

    for _ in range(student_count):
        while heap:
            count, index = heapq.heappop(heap)
            if count < rooms[index].capacity:
                break
        else:
            return None

        counts[index] += 1
        heapq.heappush(heap, (counts[index], index))

    return list(zip(rooms, counts))


def _distribution_key(distribution: list[tuple[Classroom, int]]) -> tuple:
    """Stable key used to avoid duplicate room distributions."""
    return tuple((room.room_id, placed) for room, placed in distribution)


def _room_distribution_variants(
    available_rooms: list[Classroom],
    student_count: int,
    max_options: int | None,
) -> list[list[tuple[Classroom, int]]]:
    """Return possible room splits for one exam.

    max_options=None means unlimited.  Auto Variants passes a small page limit
    from the controller, so the UI can still load unlimited variants gradually.
    The first option intentionally matches the legacy behavior: choose rooms in
    sorted order until capacity is sufficient, then balance students across that
    prefix. This keeps ClassroomAssigner.assign() backward-compatible while
    assign_variants() can expose additional valid room combinations.
    """
    if student_count == 0:
        return []

    if max_options is not None and max_options <= 0:
        return []

    options: list[list[tuple[Classroom, int]]] = []
    seen: set[tuple] = set()

    legacy = _balanced_distribution(available_rooms, student_count)
    if legacy is not None:
        key = _distribution_key(legacy)
        options.append(legacy)
        seen.add(key)

    if max_options is not None and len(options) >= max_options:
        return options

    # Generate extra combinations in deterministic order. Smaller room-count
    # combinations are tried before larger ones, and room order remains the
    # capacity-descending order supplied by the caller.
    for size in range(1, len(available_rooms) + 1):
        for room_combo in combinations(available_rooms, size):
            if sum(room.capacity for room in room_combo) < student_count:
                continue

            distribution = _balanced_distribution_for_selected_rooms(
                list(room_combo),
                student_count,
            )
            if distribution is None:
                continue

            key = _distribution_key(distribution)
            if key in seen:
                continue

            options.append(distribution)
            seen.add(key)

            if max_options is not None and len(options) >= max_options:
                return options

    return options


def _make_assignments(
    distribution: list[tuple[Classroom, int]],
    primary_offering,
    slot: TimeSlot,
    exam_date: date,
    proctor_config: ProctorConfig,
) -> list[ClassroomAssignment]:
    """Convert a room distribution into ClassroomAssignment objects."""
    return [
        ClassroomAssignment(
            exam=primary_offering,
            room=room,
            slot=slot,
            date=exam_date,
            students_assigned=placed,
            proctor_count=proctor_config.proctors_for(placed),
        )
        for room, placed in distribution
    ]


class ClassroomAssigner:
    """Create room allocations for a generated date schedule.

    assign() keeps the old single-result behavior.
    assign_variants() exposes up to a limited number of valid classroom/time-slot
    allocations for the same date-only schedule.
    """

    @staticmethod
    def _collect_exam_data(
        schedule: Schedule,
        courses_by_id: dict[str, Course],
        selected_programs: list[str],
        allow_unassigned: bool,
    ) -> tuple[list[tuple], dict[str, int]] | None:
        """Validate every exam in the schedule and gather room-sizing data.

        Returns (exam_data, unassigned) where exam_data is a list of
        (student_count, course_id, exam_date, offerings) for the exams that need
        rooms and unassigned maps unknown courses to 0. Returns None when an
        unknown course must reject the schedule (spec 4.4). Raises ValueError on
        a relevant exam missing its StudentCount (spec 4.3).

        Builds its own unassigned dict rather than mutating a caller-supplied one
        so a None reject leaves no partial state behind (immutability rule).
        """
        exam_data: list[tuple] = []
        unassigned: dict[str, int] = {}
        for course_id, exam_date in schedule.assignments.items():
            course = courses_by_id.get(course_id)
            if course is None:
                if allow_unassigned:
                    unassigned[course_id] = 0
                    continue
                return None

            # Spec §4.4: only "Exam" evaluation types are assigned to rooms.
            # Projects, Attendance, etc. keep their date but get no room.
            if not course.has_exam():
                continue

            offerings = course.get_relevant_offerings(
                selected_programs,
                schedule.period.semester,
            )

            # Spec §4.3: a relevant Exam offering MUST carry a StudentCount.
            # Silently treating a missing count as zero would hide invalid input
            # and could assign no room to a real exam. Fail clearly instead.
            missing = [o for o in offerings if o.student_count is None]
            if missing:
                raise ValueError(
                    f"Missing StudentCount for exam course '{course_id}' "
                    f"({len(missing)} relevant offering(s)). "
                    "Every relevant exam offering requires a StudentCount."
                )

            student_count = sum(offering.student_count for offering in offerings)
            exam_data.append((student_count, course_id, exam_date, offerings))
        return exam_data, unassigned

    @staticmethod
    def assign(
        schedule: Schedule,
        courses: list[Course],
        selected_programs: list[str],
        classrooms: list[Classroom],
        slots: list[TimeSlot],
        proctor_config: ProctorConfig,
        allow_unassigned: bool = False,
    ) -> Schedule | None:
        """Return the first valid classroom allocation, preserving old API."""
        return next(
            ClassroomAssigner.assign_variants(
                schedule,
                courses,
                selected_programs,
                classrooms,
                slots,
                proctor_config,
                allow_unassigned=allow_unassigned,
                max_options_per_day=1,
                max_options_per_schedule=1,
            ),
            None,
        )

    @staticmethod
    def assign_variants(
        schedule: Schedule,
        courses: list[Course],
        selected_programs: list[str],
        classrooms: list[Classroom],
        slots: list[TimeSlot],
        proctor_config: ProctorConfig,
        allow_unassigned: bool = False,
        max_options_per_day: int | None = MAX_CLASSROOM_OPTIONS_PER_DAY,
        max_options_per_schedule: int | None = MAX_CLASSROOM_OPTIONS_PER_SCHEDULE,
    ) -> Iterator[Schedule]:
        """Yield valid classroom-allocation variants for one date schedule.

        Date generation still decides which exams are on which dates. This method
        treats that result as a candidate and yields up to
        max_options_per_schedule versions enriched with classroom assignments.
        For each date, at most max_options_per_day room/slot allocations are
        considered, so one busy day cannot explode the result count.
        """
        if max_options_per_day is not None and max_options_per_day <= 0:
            return

        if max_options_per_schedule is not None and max_options_per_schedule <= 0:
            return

        courses_by_id = {course.id: course for course in courses}
        rooms = sorted(classrooms, key=lambda room: room.capacity, reverse=True)

        collected = ClassroomAssigner._collect_exam_data(
            schedule,
            courses_by_id,
            selected_programs,
            allow_unassigned,
        )
        if collected is None:
            return

        exam_data, initial_unassigned = collected

        by_date: dict[date, list[tuple]] = {}
        for item in exam_data:
            _, _, exam_date, _ = item
            by_date.setdefault(exam_date, []).append(item)

        # No exam courses to assign: keep the date schedule valid and unchanged
        # except for possible unknown-course unassigned markers.
        if not by_date:
            yield replace(
                schedule,
                classroom_assignments={},
                unassigned_classroom_exams=dict(initial_unassigned),
            )
            return

        combined: list[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]] = [
            ({}, dict(initial_unassigned))
        ]

        for exam_date in sorted(by_date):
            day_options = ClassroomAssigner._day_assignment_options(
                by_date[exam_date],
                rooms,
                slots,
                proctor_config,
                allow_unassigned,
                max_options_per_day,
            )

            if not day_options:
                return

            next_combined: list[
                tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]
            ] = []

            for current_assignments, current_unassigned in combined:
                for day_assignments, day_unassigned in day_options:
                    merged_assignments = dict(current_assignments)
                    merged_assignments.update(day_assignments)

                    merged_unassigned = dict(current_unassigned)
                    merged_unassigned.update(day_unassigned)

                    next_combined.append((merged_assignments, merged_unassigned))
                    if (
                        max_options_per_schedule is not None
                        and len(next_combined) >= max_options_per_schedule
                    ):
                        break

                if (
                    max_options_per_schedule is not None
                    and len(next_combined) >= max_options_per_schedule
                ):
                    break

            combined = next_combined
            if not combined:
                return

        final_options = (
            combined
            if max_options_per_schedule is None
            else combined[:max_options_per_schedule]
        )

        for assignments, unassigned in final_options:
            yield replace(
                schedule,
                classroom_assignments=assignments,
                unassigned_classroom_exams=unassigned,
            )

    @staticmethod
    def _day_assignment_options(
        exam_data: list[tuple],
        rooms: list[Classroom],
        slots: list[TimeSlot],
        proctor_config: ProctorConfig,
        allow_unassigned: bool,
        max_options: int | None,
    ) -> list[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]]:
        """Return valid room allocations for one date.

        max_options=None means unlimited options for that date.
        """
        options: list[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]] = []
        used_rooms: dict[TimeSlot, set[str]] = {}
        result: dict[str, list[ClassroomAssignment]] = {}
        unassigned: dict[str, int] = {}

        # Place larger exams first to reduce avoidable assignment failures.
        ordered = sorted(
            exam_data,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )

        def backtrack(index: int) -> None:
            if max_options is not None and len(options) >= max_options:
                return

            if index >= len(ordered):
                copied_result = {
                    course_id: list(assignments)
                    for course_id, assignments in result.items()
                }
                options.append((copied_result, dict(unassigned)))
                return

            student_count, course_id, exam_date, offerings = ordered[index]

            if student_count == 0:
                result[course_id] = []
                backtrack(index + 1)
                result.pop(course_id, None)
                return

            primary_offering = max(offerings, key=lambda o: o.student_count or 0)
            assigned_any_option = False

            for slot in slots:
                used_for_slot = used_rooms.setdefault(slot, set())
                available = [
                    room
                    for room in rooms
                    if room.room_id not in used_for_slot
                ]

                if sum(room.capacity for room in available) < student_count:
                    continue

                remaining_budget = (
                    None
                    if max_options is None
                    else max_options - len(options)
                )
                distributions = _room_distribution_variants(
                    available,
                    student_count,
                    remaining_budget,
                )

                for distribution in distributions:
                    assignments = _make_assignments(
                        distribution,
                        primary_offering,
                        slot,
                        exam_date,
                        proctor_config,
                    )
                    room_ids = {assignment.room.room_id for assignment in assignments}

                    result[course_id] = assignments
                    used_for_slot.update(room_ids)
                    assigned_any_option = True

                    backtrack(index + 1)

                    used_for_slot.difference_update(room_ids)
                    result.pop(course_id, None)

                    if max_options is not None and len(options) >= max_options:
                        break

                if max_options is not None and len(options) >= max_options:
                    break

            if not assigned_any_option and allow_unassigned:
                result[course_id] = []
                unassigned[course_id] = student_count
                backtrack(index + 1)
                result.pop(course_id, None)
                unassigned.pop(course_id, None)

        backtrack(0)
        return options
