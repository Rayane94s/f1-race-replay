from src.f1_data import get_race_telemetry, enable_cache, get_circuit_rotation, load_session, get_quali_telemetry, list_rounds, list_sprints
from src.run_session import run_arcade_replay, launch_insights_menu
from src.interfaces.qualifying import run_qualifying_replay
import sys
from datetime import datetime
from time import perf_counter
from src.cli.race_selection import cli_load
from src.gui.race_selection import RaceSelectionWindow
from PySide6.QtWidgets import QApplication


def _timestamp():
  return datetime.now().strftime("%H:%M:%S")


def _log(message):
  print(f"[{_timestamp()}] {message}")


def _log_step(message, started_at):
  elapsed = perf_counter() - started_at
  _log(f"{message} ({elapsed:.2f}s)")


def _lap_has_drs_activation(lap_telemetry):
  if lap_telemetry is None or "DRS" not in lap_telemetry:
    return False

  try:
    drs_values = lap_telemetry["DRS"].to_numpy()
  except Exception:
    return False

  for value in drs_values:
    try:
      if float(value) >= 10:
        return True
    except (TypeError, ValueError):
      continue
  return False


def main(year=None, round_number=None, playback_speed=1, session_type='R', visible_hud=True, ready_file=None, show_telemetry_viewer=True):
  overall_started_at = perf_counter()
  _log(f"Loading F1 {year} Round {round_number} Session '{session_type}'")

  # Enable cache for FastF1 before any session load
  cache_started_at = perf_counter()
  enable_cache()
  _log_step("FastF1 cache initialized", cache_started_at)

  session_started_at = perf_counter()
  session = load_session(year, round_number, session_type)
  _log_step(
    f"Loaded session: {session.event['EventName']} - {session.event['RoundNumber']} - {session_type}",
    session_started_at,
  )

  if session_type == 'Q' or session_type == 'SQ':

    # Get the drivers who participated and their lap times

    quali_data_started_at = perf_counter()
    qualifying_session_data = get_quali_telemetry(session, session_type=session_type)
    _log_step("Prepared qualifying telemetry dataset", quali_data_started_at)

    # Run the arcade screen showing qualifying results

    title = f"{session.event['EventName']} - {'Sprint Qualifying' if session_type == 'SQ' else 'Qualifying Results'}"
    _log_step("Session ready for replay window", overall_started_at)
    
    run_qualifying_replay(
      session=session,
      data=qualifying_session_data,
      title=title,
      ready_file=ready_file,
    )

  else:

    # Get the drivers who participated in the race

    race_data_started_at = perf_counter()
    race_telemetry = get_race_telemetry(session, session_type=session_type)
    _log_step("Prepared race telemetry dataset", race_data_started_at)

    # Get example lap for track layout
    # Prefer race lap first for faster loading. Fall back to qualifying if DRS data is missing.
    track_layout_started_at = perf_counter()
    example_lap = None
    fastest_lap = session.laps.pick_fastest()
    if fastest_lap is None:
      _log("Error: No valid laps found in session")
      return

    example_lap = fastest_lap.get_telemetry()

    if _lap_has_drs_activation(example_lap):
      _log(f"Using fastest race lap from driver {fastest_lap['Driver']} for track layout")
    else:
      _log("Race lap lacks clear DRS activation. Attempting qualifying session for DRS zones...")
      try:
        quali_started_at = perf_counter()
        quali_session = load_session(year, round_number, 'Q')
        _log_step("Loaded qualifying session for DRS zone extraction", quali_started_at)

        if quali_session is not None and len(quali_session.laps) > 0:
          fastest_quali = quali_session.laps.pick_fastest()
          if fastest_quali is not None:
            quali_telemetry = fastest_quali.get_telemetry()
            if _lap_has_drs_activation(quali_telemetry):
              example_lap = quali_telemetry
              _log(f"Using qualifying lap from driver {fastest_quali['Driver']} for DRS zones")
      except Exception as e:
        _log(f"Could not load qualifying session: {e}")

    _log_step("Track layout telemetry prepared", track_layout_started_at)

    drivers = session.drivers

    # Get circuit rotation

    circuit_rotation = get_circuit_rotation(session)
    
    # Prepare session info for display banner
    session_info = {
        'event_name': session.event.get('EventName', ''),
        'circuit_name': session.event.get('Location', ''),  # Circuit location/name
        'country': session.event.get('Country', ''),
        'year': year,
        'round': round_number,
        'date': session.event.get('EventDate', '').strftime('%B %d, %Y') if session.event.get('EventDate') else '',
        'total_laps': race_telemetry['total_laps'],
        'circuit_length_m': float(example_lap["Distance"].max()) if example_lap is not None and "Distance" in example_lap else None,
    }

    # Launch insights menu (always shown with replay)
    launch_insights_menu()
    _log("Launching insights menu...")
    _log_step("Session ready for replay window", overall_started_at)

    # Run the arcade replay

    run_arcade_replay(
      frames=race_telemetry['frames'],
      track_statuses=race_telemetry['track_statuses'],
      example_lap=example_lap,
      drivers=drivers,
      playback_speed=playback_speed,
      driver_colors=race_telemetry['driver_colors'],
      title=f"{session.event['EventName']} - {'Sprint' if session_type == 'S' else 'Race'}",
      total_laps=race_telemetry['total_laps'],
      circuit_rotation=circuit_rotation,
      visible_hud=visible_hud,
      ready_file=ready_file,
      session_info=session_info,
      session=session,
      enable_telemetry=True # This is now permanently enabled to support the telemetry insights menu if the user decides to use it
    )

if __name__ == "__main__":

  if "--cli" in sys.argv:
    # Run the CLI

    cli_load()
    sys.exit(0)

  if "--year" in sys.argv:
    year_index = sys.argv.index("--year") + 1
    year = int(sys.argv[year_index])
  else:
    year = 2025  # Default year

  if "--round" in sys.argv:
    round_index = sys.argv.index("--round") + 1
    round_number = int(sys.argv[round_index])
  else:
    round_number = 12  # Default round number

  if "--list-rounds" in sys.argv:
    list_rounds(year)
  elif "--list-sprints" in sys.argv:
    list_sprints(year)
  else:
    playback_speed = 1

  if "--viewer" in sys.argv:
  
    visible_hud = True
    if "--no-hud" in sys.argv:
      visible_hud = False

    # Session type selection
    session_type = 'SQ' if "--sprint-qualifying" in sys.argv else ('S' if "--sprint" in sys.argv else ('Q' if "--qualifying" in sys.argv else 'R'))

    # Optional ready-file path used when spawned from the GUI to signal ready state
    ready_file = None
    if "--ready-file" in sys.argv:
      idx = sys.argv.index("--ready-file") + 1
      if idx < len(sys.argv):
        ready_file = sys.argv[idx]

    main(year, round_number, playback_speed, session_type=session_type, visible_hud=visible_hud, ready_file=ready_file)
    sys.exit(0)

  # Run the GUI

  app = QApplication(sys.argv)
  win = RaceSelectionWindow()
  win.show()
  sys.exit(app.exec())
