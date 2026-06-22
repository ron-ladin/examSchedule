"""Assign rooms and time slots to every exam in a generated schedule."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import date

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
    """Split students as evenly as possible without exceeding room capacities.

    The previous implementation placed students one-by-one through a heap. That
    was correct, but with large classroom files and many generated variants it
    repeated thousands of heap operations per option. This version computes the
    same kind of balanced split in rounds, so it stays fast even when Auto
    Variants asks for many blocks.
    """
    selected: list[Classroom] = []
    total_capacity = 0

    for room in rooms:
        selected.append(room)
        total_capacity += room.capacity
        if total_capacity >= student_count:
            break

    if total_capacity < student_count:
        return None

    return _balanced_distribution_for_selected_rooms(selected, student_count)


def _balanced_distribution_for_selected_rooms(
    rooms: list[Classroom],
    student_count: int,
) -> list[tuple[Classroom, int]] | None:
    """Split students across the given rooms without exceeding capacity.

    Rooms that receive zero students are omitted. This avoids producing duplicate
    variants such as ``[Room A: 30]`` and ``[Room A: 30, Room B: 0]``.
    """
    if student_count < 0:
        return None

    if student_count == 0:
        return []

    if sum(room.capacity for room in rooms) < student_count:
        return None

    counts = [0] * len(rooms)
    active = list(range(len(rooms)))
    remaining = student_count

    while remaining > 0 and active:
        share, extra = divmod(remaining, len(active))
        assigned_this_round = 0
        next_active: list[int] = []

        for pos, index in enumerate(active):
            free_capacity = rooms[index].capacity - counts[index]
            if free_capacity <= 0:
                continue

            desired = share + (1 if pos < extra else 0)
            # When remaining < len(active), share is 0. The ``extra`` part still
            # gives one student to the first ``remaining`` rooms.
            if desired <= 0:
                desired = 1

            placed = min(free_capacity, desired)
            counts[index] += placed
            remaining -= placed
            assigned_this_round += placed

            if counts[index] < rooms[index].capacity:
                next_active.append(index)

            if remaining == 0:
                # Keep deterministic order and exit as soon as all students are
                # placed. Unused rooms will be filtered out below.
                break

        if assigned_this_round == 0:
            return None

        active = next_active

    if remaining != 0:
        return None

    return [
        (room, placed)
        for room, placed in zip(rooms, counts)
        if placed > 0
    ]


def _distribution_key(distribution: list[tuple[Classroom, int]]) -> tuple:
    """Stable key used to avoid duplicate room distributions."""
    return tuple((room.room_id, placed) for room, placed in distribution)


def _minimum_room_count(
    available_rooms: list[Classroom],
    student_count: int,
) -> int | None:
    """Return the fewest largest rooms that can contain ``student_count``."""
    total = 0
    for index, room in enumerate(available_rooms, start=1):
        total += room.capacity
        if total >= student_count:
            return index
    return None


def _room_combinations_by_capacity(
    available_rooms: list[Classroom],
    size: int,
    student_count: int,
) -> Iterator[list[Classroom]]:
    """Yield room combinations of a fixed size with capacity pruning.

    ``itertools.combinations`` is unsafe here for large inputs because it still
    walks every impossible prefix. With 1,000 classrooms, many sizes have a
    huge combinatorial space. The recursive generator below checks whether the
    best possible remaining rooms can still reach the required capacity; if not,
    it cuts the whole branch before expanding it.
    """
    room_count = len(available_rooms)
    capacities = [room.capacity for room in available_rooms]
    prefix_capacity = [0]
    for capacity in capacities:
        prefix_capacity.append(prefix_capacity[-1] + capacity)

    def top_capacity_from(start: int, count: int) -> int:
        if count <= 0:
            return 0
        if start + count > room_count:
            return -1
        return prefix_capacity[start + count] - prefix_capacity[start]

    selected: list[Classroom] = []

    def backtrack(start: int, capacity_sum: int) -> Iterator[list[Classroom]]:
        remaining_slots = size - len(selected)

        if remaining_slots == 0:
            if capacity_sum >= student_count:
                yield list(selected)
            return

        if room_count - start < remaining_slots:
            return

        # If even the largest possible remaining rooms cannot fit the exam,
        # every branch below this point is impossible.
        if capacity_sum + top_capacity_from(start, remaining_slots) < student_count:
            return

        last_start = room_count - remaining_slots
        for index in range(start, last_start + 1):
            max_after_pick = (
                capacity_sum
                + capacities[index]
                + top_capacity_from(index + 1, remaining_slots - 1)
            )
            if max_after_pick < student_count:
                # Rooms are capacity-sorted descending, so later indexes can only
                # make this branch weaker.
                break

            selected.append(available_rooms[index])
            yield from backtrack(index + 1, capacity_sum + capacities[index])
            selected.pop()

    yield from backtrack(0, 0)


def _room_distribution_variants(
    available_rooms: list[Classroom],
    student_count: int,
    max_options: int | None,
) -> Iterator[list[tuple[Classroom, int]]]:
    """Yield possible room splits for one exam lazily.

    The first option intentionally matches the legacy behavior: choose rooms in
    sorted order until capacity is sufficient, then balance students across that
    prefix. Additional options are generated one-by-one with capacity pruning;
    the function never materialises all combinations for large classroom files.
    """
    if student_count == 0:
        return

    if max_options is not None and max_options <= 0:
        return

    min_size = _minimum_room_count(available_rooms, student_count)
    if min_size is None:
        return

    emitted = 0
    seen: set[tuple] = set()

    legacy = _balanced_distribution(available_rooms, student_count)
    if legacy is not None:
        key = _distribution_key(legacy)
        seen.add(key)
        emitted += 1
        yield legacy

        if max_options is not None and emitted >= max_options:
            return

    # There is no value in assigning more rooms than students when zero-student
    # rooms are filtered out. It only creates duplicates and wastes time.
    max_size = min(len(available_rooms), student_count)

    for size in range(min_size, max_size + 1):
        for room_combo in _room_combinations_by_capacity(
            available_rooms,
            size,
            student_count,
        ):
            distribution = _balanced_distribution_for_selected_rooms(
                room_combo,
                student_count,
            )
            if distribution is None:
                continue

            key = _distribution_key(distribution)
            if key in seen:
                continue

            seen.add(key)
            emitted += 1
            yield distribution

            if max_options is not None and emitted >= max_options:
                return


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
    assign_variants() exposes valid classroom/time-slot allocations for the same
    date-only schedule without loading the whole variant space into memory.
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
        treats that result as a candidate and yields classroom-enriched variants
        lazily. The caller can take one block, keep the iterator alive, and later
        continue from the exact same point without recalculating earlier blocks.
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

        per_date_iterators: list[
            Iterator[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]]
        ] = []
        for exam_date in sorted(by_date):
            per_date_iterators.append(
                ClassroomAssigner._day_assignment_options(
                    by_date[exam_date],
                    rooms,
                    slots,
                    proctor_config,
                    allow_unassigned,
                    max_options_per_day,
                )
            )

        per_date_caches: list[
            list[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]]
        ] = [[] for _ in per_date_iterators]

        def get_day_option(day_index: int, option_index: int):
            cache = per_date_caches[day_index]
            iterator = per_date_iterators[day_index]

            while len(cache) <= option_index:
                try:
                    cache.append(next(iterator))
                except StopIteration:
                    return None

            return cache[option_index]

        chosen: list[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]] = []
        emitted = 0

        def combine(day_index: int) -> Iterator[Schedule]:
            nonlocal emitted

            if (
                max_options_per_schedule is not None
                and emitted >= max_options_per_schedule
            ):
                return

            if day_index >= len(per_date_iterators):
                merged_assignments: dict[str, list[ClassroomAssignment]] = {}
                merged_unassigned: dict[str, int] = dict(initial_unassigned)
                for day_assignments, day_unassigned in chosen:
                    merged_assignments.update(day_assignments)
                    merged_unassigned.update(day_unassigned)

                emitted += 1
                yield replace(
                    schedule,
                    classroom_assignments=merged_assignments,
                    unassigned_classroom_exams=merged_unassigned,
                )
                return

            option_index = 0
            while True:
                if (
                    max_options_per_schedule is not None
                    and emitted >= max_options_per_schedule
                ):
                    return

                option = get_day_option(day_index, option_index)
                if option is None:
                    return

                chosen.append(option)
                yield from combine(day_index + 1)
                chosen.pop()
                option_index += 1

        yield from combine(0)

    @staticmethod
    def _day_assignment_options(
        exam_data: list[tuple],
        rooms: list[Classroom],
        slots: list[TimeSlot],
        proctor_config: ProctorConfig,
        allow_unassigned: bool,
        max_options: int | None,
    ) -> Iterator[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]]:
        """Yield valid room allocations for one date lazily.

        ``max_options=None`` means unlimited options for that date, but the
        generator still produces them one at a time. This is important for very
        large classroom files: Auto Variants can stop after the current block
        instead of forcing every classroom combination to be calculated.
        """
        if max_options is not None and max_options <= 0:
            return

        emitted = 0
        used_rooms: dict[TimeSlot, set[str]] = {}
        result: dict[str, list[ClassroomAssignment]] = {}
        unassigned: dict[str, int] = {}

        # Place larger exams first to reduce avoidable assignment failures.
        ordered = sorted(
            exam_data,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )

        def backtrack(index: int) -> Iterator[tuple[dict[str, list[ClassroomAssignment]], dict[str, int]]]:
            nonlocal emitted

            if max_options is not None and emitted >= max_options:
                return

            if index >= len(ordered):
                copied_result = {
                    course_id: list(assignments)
                    for course_id, assignments in result.items()
                }
                emitted += 1
                yield (copied_result, dict(unassigned))
                return

            student_count, course_id, exam_date, offerings = ordered[index]

            if student_count == 0:
                result[course_id] = []
                yield from backtrack(index + 1)
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
                    else max_options - emitted
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

                    yield from backtrack(index + 1)

                    used_for_slot.difference_update(room_ids)
                    result.pop(course_id, None)

                    if max_options is not None and emitted >= max_options:
                        return

            if not assigned_any_option and allow_unassigned:
                result[course_id] = []
                unassigned[course_id] = student_count
                yield from backtrack(index + 1)
                result.pop(course_id, None)
                unassigned.pop(course_id, None)

        yield from backtrack(0)
