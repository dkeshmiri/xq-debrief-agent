print("XQ Family Debrief Engine is running.")

from comparison_reasoner import ComparisonReasoner
from debrief_engine import DebriefEngine
from debrief_state import (
    DebriefState,
    InteractionMode,
)
from family_repository import FamilyRepository


FAMILY_MANIFEST_PATH = (
    "data/families/demo_family.json"
)


def print_header(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()


def print_commands() -> None:
    print()
    print("Commands:")
    print("  [ENTER] / next  = continue")
    print("  ask              = ask about the active person")
    print("  family           = list family members")
    print("  switch           = switch active person")
    print("  compare          = compare two family members")
    print("  status           = show current state")
    print("  repeat           = repeat current section")
    print("  restart          = restart active debrief")
    print("  help             = show commands")
    print("  quit             = exit")


def print_family_members(
    repository: FamilyRepository,
) -> None:
    members = repository.list_members(
        debrief_enabled_only=True
    )

    print_header(
        f"{repository.family_name.upper()} MEMBERS"
    )

    for index, member in enumerate(
        members,
        start=1,
    ):
        active_marker = ""

        if (
            member["person_id"]
            == repository.active_person_id
        ):
            active_marker = " [ACTIVE]"

        print(
            f"{index}. "
            f"{member['display_name']} — "
            f"{member['family_role']}"
            f"{active_marker}"
        )


def select_family_member(
    repository: FamilyRepository,
    prompt: str,
    excluded_person_id: str | None = None,
) -> str | None:
    members = repository.list_members(
        debrief_enabled_only=True
    )

    available_members = [
        member
        for member in members
        if member["person_id"]
        != excluded_person_id
    ]

    if not available_members:
        print(
            "No eligible family members are available."
        )

        return None

    print()

    for index, member in enumerate(
        available_members,
        start=1,
    ):
        print(
            f"{index}. "
            f"{member['display_name']} — "
            f"{member['family_role']}"
        )

    print()

    selection = input(
        prompt
    ).strip()

    if not selection:
        print("Selection cancelled.")
        return None

    try:
        selected_index = int(selection) - 1
    except ValueError:
        print(
            "Enter the number of a family member."
        )
        return None

    if not (
        0
        <= selected_index
        < len(available_members)
    ):
        print(
            "That family-member selection is invalid."
        )
        return None

    return available_members[
        selected_index
    ]["person_id"]


def create_engine_for_active_person(
    repository: FamilyRepository,
) -> DebriefEngine:
    active_member = (
        repository.get_active_member()
    )

    return DebriefEngine(
        active_member["persona_file"]
    )


def run_individual_question(
    engine: DebriefEngine,
) -> None:
    engine.enter_question_mode()

    try:
        print()
        print(
            "Debrief paused at: "
            f"{engine.get_current_state().value}"
        )

        print()

        question = input(
            "Question > "
        ).strip()

        if not question:
            print()
            print("No question was entered.")
            return

        print()
        print("ANSWER:")
        print()

        print(
            engine.answer_question(
                question
            )
        )

    finally:
        engine.exit_question_mode()

    print()
    print(
        "Returning to the paused debrief section..."
    )

    print_header(
        "RESUMED"
    )

    print(
        engine.get_current_content()
    )


def run_comparison(
    repository: FamilyRepository,
    comparison_reasoner: ComparisonReasoner,
) -> None:
    members = repository.list_members(
        debrief_enabled_only=True
    )

    if len(members) < 2:
        print(
            "At least two enabled family members "
            "are required for comparison."
        )

        return

    print_header(
        "FAMILY COMPARISON"
    )

    print(
        "Select the first family member."
    )

    person_a_id = select_family_member(
        repository=repository,
        prompt="First person > ",
    )

    if person_a_id is None:
        return

    person_a_member = repository.get_member(
        person_a_id
    )

    print()
    print(
        "Select the second family member."
    )

    person_b_id = select_family_member(
        repository=repository,
        prompt="Second person > ",
        excluded_person_id=person_a_id,
    )

    if person_b_id is None:
        return

    person_b_member = repository.get_member(
        person_b_id
    )

    persona_a = repository.get_persona(
        person_a_id
    )

    persona_b = repository.get_persona(
        person_b_id
    )

    print()
    print(
        "Comparison:"
    )
    print(
        f"  {person_a_member['display_name']} "
        f"({person_a_member['family_role']})"
    )
    print(
        f"  {person_b_member['display_name']} "
        f"({person_b_member['family_role']})"
    )

    print()
    print(
        "The question must identify DISC, "
        "Driving Forces, or EQ."
    )

    print()

    question = input(
        "Comparison question > "
    ).strip()

    if not question:
        print(
            "No comparison question was entered."
        )
        return

    try:
        result = (
            comparison_reasoner.answer_question(
                question=question,
                persona_a=persona_a,
                persona_b=persona_b,
            )
        )

    except ValueError as error:
        print()
        print(
            f"Comparison could not be completed: "
            f"{error}"
        )

        return

    except Exception as error:
        print()
        print(
            "The comparison service encountered "
            "an unexpected error:"
        )
        print(error)

        return

    print()
    print_header(
        f"{result.resolved_domain.value.upper()} COMPARISON"
    )

    print(
        result.response
    )

    print()
    print(
        "Returning to the active individual debrief..."
    )


def main() -> None:
    repository = FamilyRepository(
        FAMILY_MANIFEST_PATH
    )

    engine = create_engine_for_active_person(
        repository
    )

    comparison_reasoner = (
        ComparisonReasoner(
            knowledge_dir="knowledge"
        )
    )

    print_header(
        "XQ FAMILY DEBRIEF ENGINE"
    )

    print(
        f"Family: {repository.family_name}"
    )

    print(
        f"Active persona: {engine.display_name}"
    )

    print_commands()

    print_header(
        engine.get_current_state().value.upper()
    )

    print(
        engine.get_current_content()
    )

    while True:
        print()

        command = input(
            "XQ > "
        ).strip().lower()

        if command in (
            "",
            "next",
            "continue",
        ):
            if (
                engine.get_interaction_mode()
                == InteractionMode.QUESTION
            ):
                print(
                    "Finish question mode "
                    "before continuing."
                )

                continue

            if (
                engine.get_current_state()
                == DebriefState.COMPLETE
            ):
                print(
                    "The debrief is already complete."
                )

                continue

            new_state = engine.advance()

            print_header(
                new_state.value.upper()
            )

            print(
                engine.get_current_content()
            )

        elif command == "ask":
            run_individual_question(
                engine
            )

        elif command == "family":
            print_family_members(
                repository
            )

        elif command == "switch":
            print_header(
                "SWITCH ACTIVE PERSON"
            )

            selected_person_id = (
                select_family_member(
                    repository=repository,
                    prompt="Person > ",
                )
            )

            if selected_person_id is None:
                continue

            if (
                selected_person_id
                == repository.active_person_id
            ):
                print(
                    "That person is already active."
                )

                continue

            repository.set_active_person(
                selected_person_id
            )

            engine = (
                create_engine_for_active_person(
                    repository
                )
            )

            print_header(
                "ACTIVE PERSON CHANGED"
            )

            print(
                f"Active persona: "
                f"{engine.display_name}"
            )

            print()
            print(
                "A new individual debrief "
                "has been started."
            )

            print_header(
                engine.get_current_state()
                .value
                .upper()
            )

            print(
                engine.get_current_content()
            )

        elif command == "compare":
            paused_state = (
                engine.get_current_state()
            )

            paused_mode = (
                engine.get_interaction_mode()
            )

            run_comparison(
                repository=repository,
                comparison_reasoner=(
                    comparison_reasoner
                ),
            )

            if (
                engine.get_current_state()
                != paused_state
                or engine.get_interaction_mode()
                != paused_mode
            ):
                raise RuntimeError(
                    "Comparison mode unexpectedly "
                    "changed the individual "
                    "debrief state."
                )

            print_header(
                "INDIVIDUAL DEBRIEF RESUMED"
            )

            print(
                f"Active persona: "
                f"{engine.display_name}"
            )

            print()

            print(
                engine.get_current_content()
            )

        elif command == "repeat":
            print_header(
                engine.get_current_state()
                .value
                .upper()
            )

            print(
                engine.get_current_content()
            )

        elif command == "status":
            active_member = (
                repository.get_active_member()
            )

            print(
                "Family:",
                repository.family_name,
            )

            print(
                "Active person:",
                active_member["display_name"],
            )

            print(
                "Family role:",
                active_member["family_role"],
            )

            print(
                "Current state:",
                engine.get_current_state().value,
            )

            print(
                "Interaction mode:",
                engine.get_interaction_mode().value,
            )

        elif command == "restart":
            engine.reset()

            print_header(
                "DEBRIEF RESTARTED"
            )

            print(
                engine.get_current_content()
            )

        elif command == "help":
            print_commands()

        elif command in (
            "quit",
            "exit",
        ):
            print()
            print(
                "XQ Debrief Engine stopped."
            )

            break

        else:
            print(
                "Unknown command. "
                "Enter 'help' to see available commands."
            )


if __name__ == "__main__":
    main()