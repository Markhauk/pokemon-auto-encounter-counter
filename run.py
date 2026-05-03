import argparse
import signal
import sys

from app.core.capture import get_monitors, get_physical_monitors, resolve_capture_region, save_all_monitors, save_monitor
from app.core.display import build_absolute_capture_region
from app.core.detector import EncounterCounterEngine
from app.core.exceptions import EncounterCounterError
from app.core.modes import (
    MODE_EGG_KEY,
    MODE_RANDOM_GRASS_KEY,
    MODE_SAFARI_ZONE_KEY,
)
from app.core.paths import LOCK_FILE, OUTPUT_DIR
from app.core.state_manager import SingleInstanceGuard
from app.services.config_service import ConfigService


def handle_shutdown(counter: EncounterCounterEngine, signum, frame) -> None:  # type: ignore[no-untyped-def]
    counter.log_debug(f"Received signal {signum}. Shutting down.")
    counter.stop(status="Stopped")
    sys.exit(0)


def list_monitors() -> None:
    print("Detected monitor regions:")
    for index, monitor in enumerate(get_monitors()):
        label = "all monitors" if index == 0 else f"monitor {index}"
        print(f"  {index}: {label} -> {monitor}")


def print_main_menu() -> None:
    print()
    print("=== Pokemon Counter Menu ===")
    print("1) Random grass encounter")
    print("2) Safari zone")
    print("3) Egg mode")
    print("4) Soft reset")
    print("5) Go back to screen settings (future plan)")
    print("Q) Quit")
    print()


def ask_encounter_increment(default_value: int) -> int:
    while True:
        raw_value = input(
            f"How many encounters should each detection add? [default {default_value}]: "
        ).strip()
        if raw_value == "":
            return max(1, default_value)

        try:
            value = int(raw_value)
        except ValueError:
            print("Please enter a whole number, like 1, 2, 3 or 4.")
            continue

        if value < 1:
            print("Encounter increment must be at least 1.")
            continue

        return value


def select_main_menu_option() -> str:
    while True:
        print_main_menu()
        choice = input("Select option: ").strip().lower()

        if choice in ("1", "2", "3", "4", "5", "q", "quit", "exit"):
            return choice

        print("Invalid selection. Try again.")


def configure_signal_handlers(counter: EncounterCounterEngine) -> None:
    signal.signal(signal.SIGINT, lambda s, f: handle_shutdown(counter, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown(counter, s, f))
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda s, f: handle_shutdown(counter, s, f))


def run_mode(
    *,
    args: argparse.Namespace,
    config_service: ConfigService,
    mode_key: str,
    encounter_increment: int,
) -> None:
    default_region = config_service.get_mode_region(mode_key)
    if args.monitor is None and args.region is None and args.monitor_region is None:
        capture_region = build_absolute_capture_region(
            relative_region=default_region,
            display_setup=config_service.get_display_setup(),
            physical_monitors=get_physical_monitors(),
        )
    else:
        capture_region = resolve_capture_region(
            args.monitor,
            args.region,
            args.monitor_region,
            default_region=default_region,
        )

    debug_preferences = config_service.get_debug_preferences()
    save_debug_frames = bool(args.debug or args.debug_once or debug_preferences["save_debug_frames"])
    verbose_debug = bool(args.verbose_debug or debug_preferences["verbose_debug"])

    config = config_service.load()
    config["last_selected_mode"] = mode_key
    config["encounter_increment"] = encounter_increment
    config["debug"] = {
        "save_debug_frames": save_debug_frames,
        "verbose_debug": verbose_debug,
    }
    config_service.save(config)

    with SingleInstanceGuard(LOCK_FILE):
        counter = EncounterCounterEngine(
            capture_region=capture_region,
            save_debug_frames=save_debug_frames,
            debug_once=args.debug_once,
            verbose_debug=verbose_debug,
            mode_key=mode_key,
            encounter_increment=encounter_increment,
        )
        configure_signal_handlers(counter)
        counter.run()


def run_soft_reset_mode() -> None:
    print()
    print("[TODO] Soft reset mode is not implemented yet.")
    print("Planned: reset or session tracking flow.")
    print()


def run_screen_settings_menu() -> None:
    print()
    print("[INFO] Capture settings now live in the desktop GUI and config.json.")
    print("Open the GUI and use the Capture Settings tab to edit per-mode regions.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pokemon encounter counter")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Continuously update output/last_capture.png while running.",
    )
    parser.add_argument(
        "--debug-once",
        action="store_true",
        help="Capture one frame to output/last_capture.png and exit after a mode is selected.",
    )
    parser.add_argument(
        "--verbose-debug",
        action="store_true",
        help="Print detailed image stats for each capture.",
    )
    parser.add_argument(
        "--list-monitors",
        action="store_true",
        help="Print detected monitor regions and exit.",
    )
    parser.add_argument(
        "--save-all-monitors",
        action="store_true",
        help="Save one screenshot for every monitor and exit.",
    )
    parser.add_argument(
        "--save-monitor",
        type=int,
        help="Save one screenshot for the selected full monitor and exit.",
    )
    parser.add_argument("--monitor", type=int, help="Use an entire detected monitor as the capture region.")
    parser.add_argument(
        "--region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Use explicit desktop coordinates as the capture region.",
    )
    parser.add_argument(
        "--monitor-region",
        nargs=5,
        type=int,
        metavar=("MONITOR", "LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Use coordinates relative to a selected monitor.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.list_monitors:
        list_monitors()
        return

    try:
        if args.save_all_monitors:
            for result in save_all_monitors(OUTPUT_DIR):
                print(
                    f"Saved {result['path']} -> region={result['region']}, "
                    f"mean={result['mean']:.2f}, max={result['max']}"
                )
            return

        if args.save_monitor is not None:
            result = save_monitor(OUTPUT_DIR, args.save_monitor)
            print(
                f"Saved {result['path']} -> region={result['region']}, "
                f"mean={result['mean']:.2f}, max={result['max']}"
            )
            return
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    config_service = ConfigService()
    encounter_increment = ask_encounter_increment(config_service.get_encounter_increment())

    while True:
        choice = select_main_menu_option()

        try:
            if choice == "1":
                run_mode(
                    args=args,
                    config_service=config_service,
                    mode_key=MODE_RANDOM_GRASS_KEY,
                    encounter_increment=encounter_increment,
                )
                return

            if choice == "2":
                run_mode(
                    args=args,
                    config_service=config_service,
                    mode_key=MODE_SAFARI_ZONE_KEY,
                    encounter_increment=encounter_increment,
                )
                return

            if choice == "3":
                run_mode(
                    args=args,
                    config_service=config_service,
                    mode_key=MODE_EGG_KEY,
                    encounter_increment=encounter_increment,
                )
                return

            if choice == "4":
                run_soft_reset_mode()
                continue

            if choice == "5":
                run_screen_settings_menu()
                continue

            if choice in ("q", "quit", "exit"):
                print("Goodbye.")
                return

        except (EncounterCounterError, RuntimeError, ValueError) as exc:
            print(f"[ERROR] {exc}")
            return


if __name__ == "__main__":
    main()
