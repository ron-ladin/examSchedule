"""
PLACEHOLDER: Custom Feature (Spec §4)
--------------------------------------
Spec §4.1: A new, highly valuable feature of significant complexity —
           equivalent in scope to a full version or the criteria modules.
           Forbidden: AI auto-scheduling, another simple filter/sort, minor UI tweaks.

Spec §4.2: A full requirements specification must be written for this feature
           before implementation begins.

Spec §4.3: The specification must be submitted alongside the version release.

────────────────────────────────────────────────────────────────────────────────
HOW TO USE THIS FILE
────────────────────────────────────────────────────────────────────────────────
1. The team decides on the custom feature and documents it in:
       docs/custom_feature_spec.md   (create this file)
   The spec must cover: purpose, user stories, acceptance criteria,
   data model changes, UI/UX mockups, and test plan.

2. Replace the stub classes below with the real domain model for the feature.

3. Implement adapters, engine integration, and UI in their respective layers,
   following the same Clean Architecture pattern used throughout the project:
       domain/      — pure data + invariants
       interfaces/  — abstract contracts
       adapters/    — I/O, file readers/writers
       engine/      — orchestration
       ui/          — PyQt6 screens/widgets

────────────────────────────────────────────────────────────────────────────────
CANDIDATE IDEAS (team to choose one; this list is non-binding)
────────────────────────────────────────────────────────────────────────────────
  A. Conflict Resolution Wizard — interactive UI that walks the user through
     resolving hard conflicts (mandatory exams that can't satisfy all thresholds)
     with suggested date swaps and impact preview.

  B. Room Utilisation Optimiser — given classroom capacities, assign exams to
     rooms to minimise wasted seats while respecting proctor ratios (§6.2.4).
     Generates a printable room assignment sheet.

  C. Multi-Track Export — export the final schedule in multiple formats
     simultaneously (PDF, Excel, iCal .ics) with per-programme filtering and
     branded headers.

────────────────────────────────────────────────────────────────────────────────
STUB — replace once the feature spec (§4.2) is finalised
────────────────────────────────────────────────────────────────────────────────
"""

from dataclasses import dataclass

# TODO (§4.2): write docs/custom_feature_spec.md before touching this file.
# TODO (§4.3): attach the spec to the version release PR.


@dataclass(frozen=True)
class CustomFeatureConfig:
    """Placeholder config object for the custom feature.

    Replace with a proper @dataclass(frozen=True) once the spec is settled.
    """

    # TODO: define fields based on the chosen feature (see candidates above).
    pass


@dataclass(frozen=True)
class CustomFeatureResult:
    """Placeholder result object produced by the custom feature engine.

    Replace with a proper @dataclass(frozen=True) once the spec is settled.
    """

    # TODO: define output fields based on the chosen feature.
    pass
