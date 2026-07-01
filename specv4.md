# Software Requirements Document
## Schedule Builder Application
### Feature 4: Classroom Assignment for Exams

## A. Introduction
This feature expands the existing exam scheduling system with the ability to automatically assign classrooms and time slots for each exam.
When the feature is enabled, in addition to the exam date, the system automatically allocates a time slot and appropriate exam rooms for each exam, based on the number of students and room capacities.
Additionally, the system generates a Proctor Recommendation Report, detailing the assigned rooms and the required number of proctors per room for each day and exam.
The report is available separately for each generated schedule.
This feature is optional and is added to the existing system without changing its core functionality.

## B. Detailed Requirements

### 1. General
* **1.1** The feature will be supported in both the GUI version (V2.0 extension) and the CLI version (V1.0 extension).
* **1.2** The feature is optional. The user can toggle it on or off. When off, the system operates normally without classroom assignment.
* **1.3** In the GUI version, activation will be done via a dedicated toggle in the settings screen.
* **1.4** The feature is only active when all required data is provided and valid. The "Generate" button will remain disabled until all data is complete (see section 3).

### 2. Inputs

#### 2.1 Course File Extension - Student Count
* **2.1.1** The existing courses file (`Courses.txt`) will be extended so that each study program line includes an additional optional field at the end: the number of students enrolling in that course from that program.
* **2.1.2** Extended program line format: `ProgramID, Year, Semester, Type, StudentCount`
* **2.1.3** Example:
  ```
  $$$$
  Physics 1
  83102
  Prof. O. Some
  83101,1, FALL, Obligatory, 80
  83102,1, FALL, Obligatory, 120
  Exam
  $$$$
  ```
* **2.1.4** Validation upon file upload: When the feature is enabled, the system will verify that every "Exam" course relevant to the scheduled semester includes the `StudentCount` field. If one or more courses are missing this field, an immediate error message will be displayed, and the file loading will not complete.
* **2.1.5** A `StudentCount` value of 0 means the course is skipped for room assignment and does not require a classroom.
* **2.1.6** The total number of students for an exam is calculated as the sum of students from all program lines belonging to that course, semester, and session (Moed).

#### 2.2 Classrooms File (`Classrooms.txt`)
* **2.2.1** The user will be able to upload a text file defining the list of available exam rooms.
* **2.2.2** File format:
  ```
  $$$$
  [Room Name]
  [Capacity]
  $$$$
  ```
* **2.2.3** The room name is a free text string.
* **2.2.4** The capacity is a positive integer indicating the maximum number of seats in the room.
* **2.2.5** All rooms are available throughout the entire exam period and are suitable for any exam type.

#### 2.3 Exam Time Slots
* **2.3.1** The user will define the possible times for holding exams in a day, in a 24-hour format, separated by commas.
* **2.3.2** Example: `9:00, 13:00, 19:00`
* **2.3.3** Up to 3 slots can be defined per day.
* **2.3.4** Validation:
  * a. The difference between any two consecutive times must be at least 4 hours (an exam can last up to 4 hours).
  * b. The slots must be entered in ascending order (e.g., `9:00, 19:00, 13:00` is invalid).
* **2.3.5** In the GUI version: Manual entry in the user interface.
* **2.3.6** In the CLI version: Entry via a dedicated text file in the format:
  ```
  $$$$
  9:00, 13:00, 19:00
  $$$$
  ```

#### 2.4 Proctor-Student Ratio
* **2.4.1** The user will define a ratio in the format `1:X`, where X is a positive integer greater than 0.
* **2.4.2** Example: `1:20` - one proctor for every 20 students.
* **2.4.3** The number of proctors per room is calculated as: `ceil(students_in_room / X)`.
* **2.4.4** In the GUI version: Manual entry in the user interface.
* **2.4.5** In the CLI version: Entry via a dedicated text file in the format:
  ```
  1:20
  ```

### 3. Feature Activation Conditions
* **3.1** The feature is only active when all the following data is present and valid:
  * a. All relevant "Exam" courses include `StudentCount` in the courses file.
  * b. A valid classrooms file with at least one room is loaded.
  * c. At least one time slot is defined.
  * d. A valid proctor ratio is defined.
* **3.2** In the GUI version, the "Generate" button will be disabled until all the above data is complete and valid.
* **3.3** `StudentCount` validation occurs during file upload, not during Generate. If a course is missing the count, an immediate error message will be shown in the interface.

### 4. Classroom and Slot Assignment Algorithm
* **4.1** The assignment of slots and rooms will be done automatically as part of the existing Generate process - the user does not perform manual assignment.
* **4.2** Each generated exam schedule is completely independent: each schedule has its own allocation of slots and rooms, which can vary between schedules.
* **4.3** For each exam, the total number of students is calculated: the sum of students from all program lines belonging to that course, semester, and session.
* **4.4** The algorithm will assign each exam to one of the user-defined slots.
* **4.5** Splitting between rooms: It is permissible to split a single exam across two or more rooms to cover the total number of students.
* **4.6** Room reuse: A room utilized in one slot is available for assignment in a different slot on the same day.
* **4.7** No room sharing: Two different courses cannot take place in the same room during the same slot.
* **4.8** Threshold condition - Rejected Schedule: If rooms cannot be assigned for even a single exam in a specific schedule, the entire schedule is rejected. There is no partial assignment.
* **4.9** Pre-warning message: Before executing Generate, the system will perform a feasibility check. If the total capacity of all rooms is less than the student count of any single exam, a warning message will be displayed to the user before the assignment process begins.

### 5. User Interface (GUI)
* **5.1** The feature is activated via a dedicated "Classroom Assignment" toggle in the settings screen.
* **5.2** When the feature is enabled, the following fields will be displayed:
  * a. A "Browse" button to select the classrooms file (`Classrooms.txt`).
  * b. An input field for comma-separated time slots (Example: `9:00, 13:00, 19:00`).
  * c. An input field for the proctor ratio in `1:X` format.
* **5.3** Real-time validation:
  * a. Slots field: Check for 24-hour format, ascending order, and minimum 4-hour gap between slots.
  * b. Proctor ratio: Must start with `1:` and the following number must be > 0.
* **5.4** Calendar View - Slots Display:
  * a. Exams on the same date in different slots will be displayed side-by-side in different colors (similar to a standard calendar view).
  * b. If there are more than 3 exams in the same slot and date, the slot will be displayed as a clickable record; clicking it opens the full list of exams.
* **5.5** An exam split across multiple rooms will display all the rooms assigned to it.

### 6. Output
* **6.1** The GUI calendar view will be expanded to include the assigned time slot and exam rooms.
* **6.2** Proctor Report:
  * **6.2.1** The report will be generated as a separate file from the regular schedule Export.
  * **6.2.2** The report is available for each schedule separately. In the GUI version, a proctor report can be generated for the currently displayed schedule.
  * **6.2.3** The report is available both as a view in the GUI and for export as a `.txt` file.
  * **6.2.4** Report Structure:
    ```
    Date: DD-MM-YYYY
    HH:MM
    Course Name (CourseID)
    Room Name: students_assigned/capacity | Proctors: count
    Room Name: students_assigned/capacity | Proctors: count
    Course Name (CourseID)
    ...
    HH:MM
    ...
    Date: DD-MM-YYYY
    ...
    ```
  * **6.2.5** Only dates, slots, and rooms with actual assignments will appear in the report.
  * **6.2.6** Proctor count calculation: `ceil(students_in_room / X)` where X is the denominator of the proctor ratio.

### 7. Other Assumptions & Miscellaneous
* **7.1** The number of students for an exam is calculated as the sum of students from all study programs taking that course, in the same semester and session. There is no assumption of student overlaps between different courses.
* **7.2** All rooms are available for all days of the exam period and are suitable for any exam type.
* **7.3** The maximum exam duration is 4 hours - hence the requirement for a minimum 4-hour gap between consecutive slots.
* **7.4** Courses whose evaluation type is not "Exam" (e.g., "Project") are not assigned to rooms.
* **7.5** A course with a `StudentCount` value of 0 is skipped for room assignment and does not require a classroom.

## C. Additional Terms and Explanations
* **Time Slot**: A defined time window in a day when an exam can be held (e.g., `09:00, 13:00, 19:00`). The maximum number of slots per day is 3.
* **Exam Splitting**: Dividing the students of a single exam across two or more rooms when the capacity of a single room is insufficient.
* **Classroom Assignment**: The process of allocating exam rooms and time slots for every exam in the schedule, performed automatically as part of the Generate process.
* **Proctor Ratio**: The parameter `1:X` defining how many students each single proctor supervises in a given room.
* **Proctor Report**: A document detailing for each day, slot, and exam: the list of assigned rooms, the number of students in each room, and the required number of proctors. The report is generated for a specific schedule.
* **Rejected Schedule**: An exam schedule deemed invalid due to the inability to assign rooms for one or more courses. A rejected schedule is not displayed to the user.
