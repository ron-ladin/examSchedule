# Sprint 3 Requirements - Source of Truth

## 1. General Requirements
* **1.1:** The new functionality must be supported in both the GUI version (V2.0 extension) and the file-based/CLI version (V1.0 extension).

## 2. Additional Scheduling Criteria (Thresholds / Filter Requirements)
These are mandatory threshold requirements. If a schedule does not meet these criteria, it must be invalidated/filtered out.
* Each criterion can be individually toggled ON or OFF by the user via a "Settings" screen.
* Each criterion uses a parameter `k`, which is user-defined and can hold a different value for each section.
* **2.1:** The number of days between two exams in **mandatory courses** within the same program and the same year must not be less than `k` (`k` is a positive integer).
* **2.2:** The number of days between **any two exams** (mandatory or elective) within the same program and the same year must not be less than `k` (`k` is a positive integer). Note: Counting days includes weekends and holidays.
* **2.3:** The number of collisions (same day) between two **elective courses** within the same program must not exceed `k` (`k` is a non-negative integer).
* **2.4:** The number of days between the **first mandatory exam** and the **last mandatory exam** in a specific program, year, and term must not be less than `k` (`k` is a positive integer).
* **2.5:** The maximum number of exams scheduled on the **same day** overall must not exceed `k` (`k` is a positive integer).

## 3. Optimal Scheduling Criteria (Sorting Requirements)
These criteria are used to sort/rank the valid schedules that passed the thresholds defined in Section 2.
* The user can select multiple criteria from this list and define their priority/order (primary sort, secondary sort, etc.).
* The user may change these sorting configurations at runtime without altering the threshold constraints.
* **3.1:** Sort in **descending** order by the minimum number of days between two exams in mandatory courses (same program, same year).
* **3.2:** Sort in **descending** order by the average number of days between any two exams (mandatory or elective, same program, same year).
* **3.3:** Sort in **descending** order by the number of collisions between two elective courses (same program).
* **3.4:** Sort in **descending** order by the number of days between the first mandatory exam and the last mandatory exam (same program, year, term).
* **3.5:** Sort in **descending** order by the maximum number of exams scheduled on the same day.

## 4. Customer Value Expansion (Custom Feature)
* **4.1:** We must design and implement a new, highly valuable feature of significant complexity (equivalent to a full version or the criteria modules above). *Note: AI auto-scheduling, adding just another simple filter/sort, or minor UI tweaks are strictly forbidden.*
* **4.2:** We must write a full requirements specification documenting this new feature, its required capabilities, and enabled attributes.
* **4.3:** This specification must be submitted alongside the version release.

<!-- PLACEHOLDER: Custom Feature Specification
     To be defined by the team. Requirements for Section 4 must be documented here
     before implementation begins. See Section 4.2 for required contents.
-->

## 5. Software Design
* **5.1:** The system must be written in Python (or C++).
* **5.2:** The software design must strictly follow Object-Oriented Programming (OOP) principles.

## 6. Performance
* **6.1:** Internal Data Caching: It is highly recommended to cache internal data. If the courses/dates input files have not changed, data should be loaded from an internal save rather than parsing the raw files again.
* **6.2:** UI Responsiveness: The UI must be highly responsive. Any freeze, delay, or unresponsiveness lasting more than 1 second is considered a failure.

## 7. Workflow and Methodology
* **7.1:** Development will use Git (individual accounts) and Jira for project management.
* **7.2:** A designated "Version Lead" will manage the main development branch and assign Jira tasks.
* **7.3:** Development must follow Agile methodology, including:
  - Software Requirements (especially for the custom feature in section 4).
  - Software Design (including UI/UX, menus, and use-case examples).
  - Test Planning (detailed in a test spec document).
  - Implementation (Git commits).
  - Code-Review (documented in a summary file).
  - Execution of the test plan.
