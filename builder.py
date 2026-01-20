import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional
import re
import yaml
from colorama import init, Fore, Style
from collections import defaultdict
import webbrowser

# Initialize colorama
init(autoreset=True)

# Constants
DEFAULT_STAGING_NAME = "__DEFAULT__"


def open_presets_in_editor():
    """Open the build_presets.yaml file in the default editor"""
    config_path = SCRIPT_DIR / "build_presets.yaml"
    if not config_path.exists():
        print(Fore.RED + f"Error: Configuration file not found at {config_path}")
        sys.exit(1)

    try:
        print(Fore.CYAN + f"Opening {config_path} in default editor...")
        if sys.platform.startswith("win"):
            os.startfile(config_path)
        elif sys.platform.startswith("darwin"):  # macOS
            subprocess.call(["open", config_path])
        else:  # Linux and others
            subprocess.call(["xdg-open", config_path])
        print(Fore.GREEN + "Build presets file opened successfully.")
    except Exception as e:
        print(Fore.RED + f"Error opening file: {e}")
        print(Fore.YELLOW + f"You can manually open the file at: {config_path}")
        sys.exit(1)


# --- Configuration ---
SCRIPT_DIR = Path.cwd()


def load_config() -> Dict[str, Any]:
    """Loads the build presets configuration file."""
    config_path = SCRIPT_DIR / "build_presets.yaml"
    if not config_path.exists():
        print(Fore.RED + f"Error: Configuration file not found at {config_path}")
        sys.exit(1)
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Resolve relative paths in config relative to SCRIPT_DIR
        for key in [
            "uproject_path",
            "staging_dir",
            "package_dir",
            "repack_script_path",
        ]:
            if key in config and config[key]:
                path_val = Path(config[key])
                if not path_val.is_absolute():
                    config[key] = str((SCRIPT_DIR / path_val).resolve())

        return config
    except yaml.YAMLError as e:
        print(Fore.RED + f"Error parsing YAML file: {e}")
        sys.exit(1)


def _get_enabled_presets(all_presets: Dict[str, Any]) -> Dict[str, Any]:
    """Filters the presets dictionary, returning only those that are enabled."""
    if not all_presets:
        return {}
    return {
        name: data for name, data in all_presets.items() if data.get("enabled", True)
    }


# --- Utility Functions ---
def clean_directory(dir_path: Path):
    if dir_path.exists() and dir_path.is_dir():
        shutil.rmtree(dir_path)


def run_command(
    cmd: List[str],
    cwd: Path,
    step_name: str,
    filters: Optional[List[Tuple[str, str]]] = None,
    collect_pre_summary_errors: bool = False,
):
    print(Fore.CYAN + f"  - Running {step_name} from: {cwd}")
    if filters:
        print(
            Fore.CYAN + f"    (Applying {len(filters)} output filter(s) for this step)"
        )
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Use a defaultdict to group unique errors by file path
        collected_errors = defaultdict(set)
        is_collecting = collect_pre_summary_errors

        # Regex to capture: Group 1 (Full File Path), Group 2 (Error Message)
        # Changed (?:.*?\\)? to capture the full path in group 1
        bp_error_pattern = re.compile(
            r"LogBlueprint:\s+Error:\s+\[AssetLog\]\s+(.*?\.uasset):\s+(.*?)(?:\s+from\s+Source:.*)?$",
            re.IGNORECASE,
        )

        if process.stdout:
            for line in process.stdout:
                line_stripped = line.strip()

                # If we are collecting, check for the summary line to stop collection
                if is_collecting and "LogInit: Display: Warning/Error Summary" in line:
                    is_collecting = False

                # If collection is active, capture lines with error/warning signatures
                if is_collecting and (": Error:" in line):
                    # Try to match the specific Blueprint Asset Log format
                    match = bp_error_pattern.search(line_stripped)
                    if match:
                        file_path = match.group(
                            1
                        )  # e.g. "C:\Users\...\PDA_EMM_Sorting.uasset"
                        error_msg = match.group(
                            2
                        )  # e.g. "[Compiler] In use pin Condition no longer exists..."
                        collected_errors[file_path].add(error_msg)
                    else:
                        # Fallback for generic errors not matching the pattern
                        collected_errors["General/System Errors"].add(line_stripped)

                # Apply standard output filtering
                is_filtered = False
                if filters:
                    for match_type, pattern in filters:
                        if (
                            match_type == "startswith"
                            and line_stripped.startswith(pattern)
                        ) or (match_type == "contains" and pattern in line):
                            is_filtered = True
                            break
                if not is_filtered:
                    print(line, end="")

        process.wait()

        # After the process is complete, print the structured summary
        if collected_errors:
            print(Fore.YELLOW + Style.BRIGHT + "\n" + "=" * 60)
            print(
                Fore.YELLOW
                + Style.BRIGHT
                + "--- Summary of Unique Compilation Errors ---"
            )
            print(Fore.YELLOW + Style.BRIGHT + "=" * 60)

            # Sort paths alphabetically
            sorted_paths = sorted(collected_errors.keys())

            for file_path in sorted_paths:
                error_set = collected_errors[file_path]

                if file_path == "General/System Errors":
                    print(Fore.RED + Style.BRIGHT + f"\n[ General / System Errors ]")
                else:
                    # Print the full path
                    print(Fore.CYAN + Style.BRIGHT + f"\nFile: {file_path}")

                for err in sorted(list(error_set)):
                    # Color formatting to make [Compiler] pop
                    formatted_err = err.replace(
                        "[Compiler]", Fore.MAGENTA + "[Compiler]" + Fore.RED
                    )
                    print(Fore.RED + f"  -> {formatted_err}")

            print(Fore.YELLOW + Style.BRIGHT + "=" * 60)

        if process.returncode != 0:
            print(
                Fore.RED
                + f"\n--- ERROR during {step_name} (Code: {process.returncode}) ---"
            )
            sys.exit(1)
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred during {step_name}: {e}")
        sys.exit(1)


def _expand_variables(value: str, variables: Dict[str, str], max_depth=5) -> str:
    if max_depth <= 0:
        raise ValueError(
            "Variable expansion depth exceeded. Check for circular references."
        )
    matches = re.findall(r"\{([^{}]+)\}", value)
    if not matches:
        return value
    for var_name in matches:
        if var_name in variables:
            expanded_var = _expand_variables(
                variables[var_name], variables, max_depth - 1
            )
            value = value.replace(f"{{{var_name}}}", expanded_var)
    return value


def _resolve_cook_paths(
    raw_list: List[str], variables: Dict[str, str], aliases: Dict[str, List[str]]
) -> Set[str]:
    resolved = set()
    for item in raw_list:
        if item.startswith("@"):
            alias_name = item[1:]
            if alias_name in aliases:
                resolved.update(
                    _resolve_cook_paths(aliases[alias_name], variables, aliases)
                )
            else:
                print(
                    Fore.YELLOW
                    + f"    - Warning: Nocook alias '@{alias_name}' not found in configuration."
                )
        else:
            resolved.add(_expand_variables(item, variables))
    return resolved


def _process_cook_exceptions(
    never_cook_paths: Set[str], to_cook_paths: Set[str], content_root: Path
) -> List[str]:
    if not to_cook_paths:
        return sorted(list(never_cook_paths))
    print(Fore.CYAN + "  - Processing 'directories_to_cook' exceptions...")
    final_never_cook = set(never_cook_paths)
    for cook_path_str in to_cook_paths:
        cook_path = Path(cook_path_str)
        is_overridden = False
        for never_path_str in never_cook_paths:
            if cook_path.is_relative_to(never_path_str):
                is_overridden = True
                break
        if not is_overridden:
            print(
                Fore.YELLOW
                + f"    - Warning: 'to_cook' path '{cook_path_str}' does not fall under any 'never_cook' directory. Rule has no effect."
            )
            continue
        parent_never_cook = None
        for never_path_str in never_cook_paths:
            if cook_path.is_relative_to(never_path_str):
                if parent_never_cook is None or Path(never_path_str).is_relative_to(
                    parent_never_cook
                ):
                    parent_never_cook = Path(never_path_str)
        if not parent_never_cook:
            continue
        final_never_cook.discard(parent_never_cook.as_posix())
        current_path_parts = list(parent_never_cook.parts)
        path_to_walk = cook_path.relative_to(parent_never_cook)
        for part in path_to_walk.parts:
            current_path_on_disk = content_root.joinpath(*current_path_parts)
            if not current_path_on_disk.is_dir():
                break
            for sibling in current_path_on_disk.iterdir():
                if sibling.is_dir() and sibling.name != part:
                    path_to_exclude = Path(*current_path_parts, sibling.name)
                    final_never_cook.add(path_to_exclude.as_posix())
            current_path_parts.append(part)
    print(
        Fore.CYAN
        + f"    - Final 'never_cook' list contains {len(final_never_cook)} specific paths after processing exceptions."
    )
    return sorted(list(final_never_cook))


def _apply_temp_cook_settings(
    project_dir: Path, directories_to_never_cook: List[str]
) -> Optional[Path]:
    print(Fore.CYAN + "  - Applying temporary cooking settings to Game.ini...")
    ini_path = (
        project_dir / "Intermediate" / "Config" / "CoalescedSourceConfigs" / "Game.ini"
    )
    if not directories_to_never_cook:
        return None
    if not ini_path.exists():
        return None
    backup_path = ini_path.with_suffix(".ini.bak")
    shutil.copy2(ini_path, backup_path)
    print(Fore.CYAN + f"    - Backed up '{ini_path.name}' to '{backup_path.name}'")
    processed_paths = [
        f"/Game/{entry.replace(os.sep, '/')}" for entry in directories_to_never_cook
    ]
    new_settings_lines = [
        f'DirectoriesToNeverCook=(Path="{path}")\n' for path in processed_paths
    ]
    output_lines, in_packaging_section, section_updated = [], False, False
    with open(ini_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        stripped_line = line.strip()
        if stripped_line == "[/Script/UnrealEd.ProjectPackagingSettings]":
            in_packaging_section = True
            output_lines.append(line)
        elif in_packaging_section and stripped_line.startswith("["):
            if not section_updated:
                output_lines.extend(new_settings_lines)
                section_updated = True
            in_packaging_section = False
            output_lines.append(line)
        elif in_packaging_section and stripped_line.startswith(
            "DirectoriesToNeverCook="
        ):
            continue
        else:
            output_lines.append(line)
    if in_packaging_section and not section_updated:
        output_lines.extend(new_settings_lines)
    with open(ini_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)
    print(
        Fore.GREEN
        + f"    - Successfully updated 'DirectoriesToNeverCook' with {len(processed_paths)} entries."
    )
    return backup_path


def _restore_ini_backup(backup_path: Optional[Path]):
    if backup_path and backup_path.exists():
        try:
            original_path = backup_path.with_suffix("")
            shutil.move(str(backup_path), str(original_path))
            print(
                Fore.GREEN
                + f"\n  - Successfully restored '{original_path.name}' from backup."
            )
        except Exception as e:
            print(Fore.RED + f"\n  - ERROR: Failed to restore backup: {e}")


def run_single_cook(
    config: Dict[str, Any], output_subdir_name: str, cook_config: Dict[str, Any]
):
    print(
        Fore.GREEN
        + Style.BRIGHT
        + f"\n--- Starting Cook for: '{output_subdir_name}' ---"
    )
    variables, aliases = config.get("variables", {}), config.get("nocook_aliases", {})
    print(Fore.CYAN + "  - Resolving cook/nocook lists from config...")
    never_cook_raw, to_cook_raw = cook_config.get(
        "directories_to_never_cook", []
    ), cook_config.get("directories_to_cook", [])
    initial_never_cook, initial_to_cook = _resolve_cook_paths(
        never_cook_raw, variables, aliases
    ), _resolve_cook_paths(to_cook_raw, variables, aliases)
    uproject, ue4cmd = config["uproject_path"], config["ue4_cmd_path"]
    ue_project_dir = Path(uproject).parent
    content_root = ue_project_dir / "Content"
    final_never_cook_list = _process_cook_exceptions(
        initial_never_cook, initial_to_cook, content_root
    )
    staging_root, ue_cooked_fsd_dir = (
        Path(config["staging_dir"]),
        ue_project_dir / "Saved" / "Cooked" / "WindowsNoEditor" / "FSD",
    )
    ini_backup_path = None
    try:
        ini_backup_path = _apply_temp_cook_settings(
            ue_project_dir, final_never_cook_list
        )
        ue_cook_filters = [
            ("startswith", "LogPython"),
            ("startswith", "LogPluginManager"),
            ("startswith", "LogGameplayTags"),
            ("contains", "Display: Loaded TargetPlatform"),
            ("contains", "is not initialized properly"),
            ("contains", "but it was never saved as an export"),
            ("contains", "has been saved with empty engine version"),
            ("contains", "when exposed to Python."),
            ("contains", ": Can't find file."),
        ]
        cook_cmd = [
            ue4cmd,
            uproject,
            "-run=Cook",
            "-TargetPlatform=WindowsNoEditor",
            "-ddc=InstalledDerivedDataBackendGraph",
            "-unversioned",
            "-fileopenlog",
            "-stdout",
            "-CrashForUAT",
            "-unattended",
            "-NoLogTimes",
            "-UTF8Output",
        ]
        run_command(
            cook_cmd,
            ue_project_dir,
            "UE4 Cooker",
            filters=ue_cook_filters,
            collect_pre_summary_errors=True,
        )
        target_staged_fsd_dir = staging_root / output_subdir_name / "FSD"
        print(
            Fore.CYAN
            + f"  - Moving cooked FSD folder to staging area: {target_staged_fsd_dir}"
        )
        clean_directory(target_staged_fsd_dir.parent)
        target_staged_fsd_dir.parent.mkdir(parents=True, exist_ok=True)
        if not ue_cooked_fsd_dir.exists():
            print(
                Fore.RED
                + f"Error: Cooker output 'FSD' folder not found at {ue_cooked_fsd_dir.parent}"
            )
            sys.exit(1)
        shutil.move(str(ue_cooked_fsd_dir), str(target_staged_fsd_dir))
        print(Fore.CYAN + "  - Performing asset cleanup...")
        for item in target_staged_fsd_dir.iterdir():
            if item.name.lower() not in ["content", "assetregistry.bin"]:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
    finally:
        _restore_ini_backup(ini_backup_path)
    print(
        Fore.GREEN + Style.BRIGHT + f"--- Cook Complete for '{output_subdir_name}' ---"
    )


def cook_assets(config: Dict[str, Any], specific_presets: List[str]):
    """Orchestrates the cooking process based on requested presets."""
    print(Fore.GREEN + Style.BRIGHT + "=== Starting Cook Process ===")
    default_cook_config = config.get("cook_settings", {})
    all_presets = config.get("presets", {})
    if not specific_presets:
        print(Fore.CYAN + f"No specific presets requested. Running DEFAULT cook.")
        run_single_cook(config, DEFAULT_STAGING_NAME, default_cook_config)
    else:
        for preset_name in specific_presets:
            if preset_name not in all_presets:
                print(
                    Fore.RED
                    + f"\n--- ERROR: Preset '{preset_name}' not found in build_presets.yaml ---"
                )
                sys.exit(1)
            if not all_presets[preset_name].get("enabled", True):
                print(
                    Fore.YELLOW
                    + f"\n- Skipping cook for '{preset_name}': Preset is disabled in config."
                )
                continue
            preset_data = all_presets[preset_name]
            cook_override = preset_data.get("cook_override")
            if cook_override:
                print(Fore.CYAN + f"\nPreset '{preset_name}' has a cook override.")
                run_single_cook(config, preset_name, cook_override)
            else:
                print(
                    Fore.CYAN
                    + f"\nPreset '{preset_name}' uses default cook settings. Running default cook if necessary..."
                )
                run_single_cook(config, DEFAULT_STAGING_NAME, default_cook_config)
    print(Fore.GREEN + Style.BRIGHT + "\n=== All Requested Cooks Complete ===")


# --- Asset Packing Logic ---


def _resolve_asset_paths(
    patterns: List[str], search_dir: Path
) -> Tuple[Set[Path], Set[str]]:
    resolved_paths, unresolved_patterns = set(), set()
    for pattern in patterns:
        found_for_this_pattern = set()
        is_bare_name, is_dir_path = not any(
            c in pattern for c in "*/\\."
        ), pattern.endswith(("/", "\\"))
        if is_bare_name:
            for path in search_dir.rglob(f"{pattern}.*"):
                if path.is_file():
                    found_for_this_pattern.add(path)
        elif is_dir_path:
            dir_path = search_dir / pattern
            if dir_path.is_dir():
                for path in dir_path.rglob("*"):
                    if path.is_file():
                        found_for_this_pattern.add(path)
        else:
            try:
                for path in search_dir.glob(pattern):
                    if path.is_file():
                        found_for_this_pattern.add(path)
                    elif path.is_dir():
                        for sub_path in path.rglob("*"):
                            if sub_path.is_file():
                                found_for_this_pattern.add(sub_path)
            except Exception:
                pass
        if found_for_this_pattern:
            resolved_paths.update(found_for_this_pattern)
        else:
            if not list(search_dir.glob(pattern)):
                unresolved_patterns.add(pattern)
    return resolved_paths, unresolved_patterns


def _resolve_asset_ownership(
    presets_to_pack: Dict[str, Any], search_root_dir: Path
) -> Tuple[Dict[Path, str], Dict[str, List[str]], Dict[str, Dict[Path, str]]]:
    print(Fore.CYAN + "  - Pass 1: Resolving asset ownership and friendships...")
    friend_map = {
        name: preset.get("friends", []) for name, preset in presets_to_pack.items()
    }
    preset_asset_maps = {}
    for mod_name, preset_data in presets_to_pack.items():
        asset_config = preset_data.get("assets", {})
        if isinstance(asset_config, list):
            asset_config = {"shared": asset_config}
        include_patterns, shared_patterns, exclude_patterns = (
            asset_config.get("include", []),
            asset_config.get("shared", []),
            asset_config.get("exclude", []),
        )
        _, unresolved = _resolve_asset_paths(
            include_patterns + shared_patterns + exclude_patterns, search_root_dir
        )
        if unresolved:
            print(
                Fore.RED
                + f"\n--- ERROR: Could not find the following assets for mod '{mod_name}': ---"
            )
            print(Fore.RED + f"    (Searched in: {search_root_dir})")
            for pattern in sorted(unresolved):
                print(Fore.RED + f"  - {pattern}")
            sys.exit(1)

        def get_ownership_map(patterns: List[str]) -> Dict[Path, str]:
            ownership = {}
            for p in patterns:
                paths, _ = _resolve_asset_paths([p], search_root_dir)
                for path in paths:
                    if path not in ownership or len(p) > len(ownership[path]):
                        ownership[path] = p
            return ownership

        include_map, shared_map, exclude_map = (
            get_ownership_map(include_patterns),
            get_ownership_map(shared_patterns),
            get_ownership_map(exclude_patterns),
        )
        resolved_map, warnings = {}, []
        for path in (
            set(include_map.keys()) | set(shared_map.keys()) | set(exclude_map.keys())
        ):
            contenders = []
            if path in include_map:
                contenders.append(
                    (len(include_map[path]), 2, "include", include_map[path])
                )
            if path in shared_map:
                contenders.append(
                    (len(shared_map[path]), 1, "shared", shared_map[path])
                )
            if path in exclude_map:
                contenders.append(
                    (len(exclude_map[path]), 0, "exclude", exclude_map[path])
                )
            contenders.sort(key=lambda x: (x[0], x[1]), reverse=True)
            winner_type, winner_pattern = contenders[0][2], contenders[0][3]
            if winner_type in ["include", "shared"]:
                resolved_map[path] = winner_type
                if path in exclude_map:
                    warnings.append(
                        f"'{path.relative_to(search_root_dir)}' {winner_type} by '{winner_pattern}' overriding exclude '{exclude_map[path]}'"
                    )
        if warnings:
            print(Fore.YELLOW + f"  - Overlap warnings for '{mod_name}':")
            for w in sorted(warnings):
                print(Fore.YELLOW + f"    - {w}")
        preset_asset_maps[mod_name] = resolved_map
    ownership_map, potential_owners = {}, {}
    for mod_name, assets in preset_asset_maps.items():
        for path, rule in assets.items():
            if rule == "include":
                if path not in potential_owners:
                    potential_owners[path] = []
                potential_owners[path].append(mod_name)
    conflicts = [
        f"  - Asset '{path.relative_to(search_root_dir)}' is exclusively claimed by multiple mods: {', '.join(owners)}"
        for path, owners in potential_owners.items()
        if len(owners) > 1
    ]
    if conflicts:
        print(Fore.RED + "\n--- ERROR: Asset ownership conflict detected: ---")
        for c in sorted(conflicts):
            print(Fore.RED + c)
        sys.exit(1)
    for path, owners in potential_owners.items():
        ownership_map[path] = owners[0]
    print(Fore.GREEN + "  - Pass 1 Complete.")
    return ownership_map, friend_map, preset_asset_maps


def _stage_and_pack_mod(
    mod_name: str,
    config: Dict[str, Any],
    ownership_map: Dict[Path, str],
    friend_map: Dict[str, List[str]],
    asset_map: Dict[Path, str],
    validation_root_dir: Path,
):
    modding_dir, staging_root, package_dir = (
        SCRIPT_DIR,
        Path(config["staging_dir"]),
        Path(config["package_dir"]),
    )
    print(Fore.CYAN + f"\n- Processing mod: '{mod_name}'")

    preset_specific_staging = staging_root / mod_name / "FSD" / "Content"
    default_staging = staging_root / DEFAULT_STAGING_NAME / "FSD" / "Content"

    staged_fsd_content_dir = None
    if preset_specific_staging.exists():
        staged_fsd_content_dir = preset_specific_staging
        print(Fore.CYAN + f"  - Using dedicated cook from: {staged_fsd_content_dir}")
    elif default_staging.exists():
        staged_fsd_content_dir = default_staging
        print(Fore.CYAN + f"  - Using default cook from: {staged_fsd_content_dir}")
    else:
        print(Fore.RED + f"\n--- ERROR: No cooked assets found for '{mod_name}'. ---")
        print(
            Fore.RED
            + f"Expected either:\n  - {preset_specific_staging}\n  - {default_staging}"
        )
        sys.exit(1)

    final_asset_paths, access_errors = set(), []
    for path, rule in asset_map.items():
        relative_path = path.relative_to(validation_root_dir)
        actual_source_path = staged_fsd_content_dir / relative_path
        owner = ownership_map.get(path)
        if rule == "include":
            if owner == mod_name:
                final_asset_paths.add(actual_source_path)
        elif rule == "shared":
            if owner is None or owner == mod_name:
                final_asset_paths.add(actual_source_path)
            elif mod_name not in friend_map.get(owner, []):
                access_errors.append(
                    f"  - Cannot use asset '{relative_path}' owned by '{owner}', as '{mod_name}' is not a friend."
                )
            else:
                final_asset_paths.add(actual_source_path)

    if access_errors:
        print(
            Fore.RED
            + f"\n--- ERROR: Asset access violation found for mod '{mod_name}': ---"
        )
        for error in sorted(access_errors):
            print(Fore.RED + error)
        sys.exit(1)

    if not final_asset_paths:
        print(Fore.YELLOW + f"  - Skipping mod '{mod_name}': No assets to package.")
        return

    missing_assets = [p for p in final_asset_paths if not p.exists()]
    if missing_assets:
        print(
            Fore.RED
            + f"\n--- ERROR: The following assets are missing from the cook source '{staged_fsd_content_dir}': ---"
        )
        for m in missing_assets:
            print(Fore.RED + f"  - {m.relative_to(staged_fsd_content_dir)}")
        sys.exit(1)

    build_dir = modding_dir / f"build_{mod_name}"
    pack_source_content_dir = build_dir / "FSD" / "Content"

    clean_directory(build_dir)
    pack_source_content_dir.mkdir(parents=True, exist_ok=True)

    asset_registry_src = staged_fsd_content_dir.parent / "AssetRegistry.bin"
    if asset_registry_src.exists():
        shutil.copy2(asset_registry_src, build_dir / "FSD")

    print(Fore.CYAN + f"  - Staging {len(final_asset_paths)} assets...")
    for asset_path in sorted(list(final_asset_paths)):
        relative_path = asset_path.relative_to(staged_fsd_content_dir)
        dest_path = pack_source_content_dir / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_path, dest_path)

    global_overrides = config.get("global_overrides", [])
    for override in global_overrides:
        _apply_override(override, build_dir / "FSD", "global")

    all_presets = config.get("presets", {})

    if mod_name in all_presets:
        preset_overrides = all_presets[mod_name].get("overrides", [])
        for override in preset_overrides:
            _apply_override(override, build_dir / "FSD", mod_name)

    print(Fore.CYAN + f"  - Packing '{mod_name}'...")
    pak_output = run_unrealpak(build_dir / "FSD", SCRIPT_DIR, mod_name)

    final_mod_dir = package_dir / mod_name
    final_mod_dir.mkdir(parents=True, exist_ok=True)

    if (build_dir / "FSD.pak").exists():
        shutil.move(str(build_dir / "FSD.pak"), str(final_mod_dir / f"{mod_name}.pak"))
    else:
        print(
            Fore.RED
            + f"  - Error: Repack script did not generate 'FSD.pak' in '{build_dir}'."
        )

    clean_directory(build_dir)


def pack_assets(config: Dict[str, Any], specific_presets: List[str]):
    print(Fore.GREEN + Style.BRIGHT + "=== Starting Pack Process ===")
    default_staged_content_dir = (
        Path(config["staging_dir"]) / DEFAULT_STAGING_NAME / "FSD" / "Content"
    )
    if not default_staged_content_dir.is_dir():
        print(
            Fore.RED
            + f"Error: Default staged content not found at '{default_staged_content_dir}'."
        )
        print(
            Fore.RED
            + "You must run 'python build.py cook' (without arguments) at least once before packing."
        )
        sys.exit(1)
    Path(config["package_dir"]).mkdir(parents=True, exist_ok=True)
    all_presets = config.get("presets", {})
    enabled_presets = _get_enabled_presets(all_presets)
    presets_to_pack = {}
    if specific_presets:
        print(
            Fore.CYAN
            + f"--- Packing specific presets: {', '.join(specific_presets)} ---"
        )
        for name in specific_presets:
            if name not in all_presets:
                print(
                    Fore.RED
                    + f"\n--- ERROR: Preset '{name}' not found in build_presets.yaml ---"
                )
                sys.exit(1)
            if name not in enabled_presets:
                print(
                    Fore.YELLOW + f"- Skipping '{name}': Preset is disabled in config."
                )
                continue
            presets_to_pack[name] = enabled_presets[name]
        if not presets_to_pack:
            print(
                Fore.YELLOW
                + "\nAll specified presets are disabled or do not exist. Nothing to pack."
            )
            return
    else:
        print(Fore.CYAN + "--- Packing all available ENABLED presets ---")
        presets_to_pack = enabled_presets
    if not presets_to_pack:
        print(Fore.YELLOW + "No enabled presets found to pack.")
        return
    ownership_map, friend_map, preset_asset_maps = _resolve_asset_ownership(
        presets_to_pack, default_staged_content_dir
    )
    print(Fore.CYAN + "\n  - Pass 2 & 3: Validating, staging, and packing mods...")
    for preset_name in presets_to_pack.keys():
        asset_map = preset_asset_maps.get(preset_name, {})
        _stage_and_pack_mod(
            preset_name,
            config,
            ownership_map,
            friend_map,
            asset_map,
            default_staged_content_dir,
        )
    if config.get("package_unlisted_assets", False) and not specific_presets:
        print(
            Fore.CYAN
            + "\n- Checking for unlisted assets in the DEFAULT cook to auto-package..."
        )
        all_top_level_dirs = {
            d.name for d in default_staged_content_dir.iterdir() if d.is_dir()
        }
        _, _, all_preset_asset_maps = _resolve_asset_ownership(
            all_presets, default_staged_content_dir
        )
        referenced_top_level_dirs = set()
        for asset_map in all_preset_asset_maps.values():
            for path in asset_map.keys():
                try:
                    referenced_top_level_dirs.add(
                        path.relative_to(default_staged_content_dir).parts[0]
                    )
                except (ValueError, IndexError):
                    continue
        unlisted_folders = all_top_level_dirs - referenced_top_level_dirs
        if not unlisted_folders:
            print(Fore.CYAN + "  - No unlisted asset folders found to package.")
        else:
            print(
                Fore.CYAN
                + f"  - Found {len(unlisted_folders)} unlisted folder(s) to package..."
            )
            for asset_folder in sorted(list(unlisted_folders)):
                print(Fore.CYAN + f"  - Auto-packaging: {asset_folder}")
                unlisted_preset_data = {"assets": {"include": [f"{asset_folder}/"]}}
                ownership, friends, assets = _resolve_asset_ownership(
                    {asset_folder: unlisted_preset_data}, default_staged_content_dir
                )
                _stage_and_pack_mod(
                    asset_folder,
                    config,
                    ownership,
                    friends,
                    assets.get(asset_folder, {}),
                    default_staged_content_dir,
                )
    print(Fore.GREEN + Style.BRIGHT + "\n=== Pack Process Complete ===")


def run_unrealpak(fsd_path: Path, script_dir: Path, pak_name: str):
    """
    Runs UnrealPak to create a .pak file from an FSD directory.
    Replaces the old repack.bat script.
    """
    unrealpak_exe = (
        script_dir / "UnrealPak" / "Engine" / "Binaries" / "Win64" / "UnrealPak.exe"
    )

    if not unrealpak_exe.exists():
        print(Fore.RED + f"Error: UnrealPak.exe not found at: {unrealpak_exe}")
        sys.exit(1)

    # Create autogen.txt with file mappings
    autogen_path = script_dir / "autogen.txt"
    pak_output = fsd_path.with_suffix(".pak")

    # Write the mapping file
    with open(autogen_path, "w") as f:
        f.write(f'"{fsd_path}\\*.*" "..\\..\\..\\FSD\\*.*"\n')

    print(Fore.CYAN + f"  - Creating {pak_name}.pak with UnrealPak...")

    # Run UnrealPak
    cmd = [
        str(unrealpak_exe),
        str(pak_output),
        "-platform=Windows",
        f"-create={autogen_path}",
        "-compress",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=script_dir,
        )

        if process.stdout:
            for line in process.stdout:
                line_stripped = line.strip()

                # Color different types of output
                if "Warning:" in line:
                    print(Fore.YELLOW + "    " + line, end="")
                elif "Error:" in line:
                    print(Fore.RED + "    " + line, end="")
                elif "Added" in line and "files" in line:
                    print(Fore.GREEN + Style.BRIGHT + "    " + line, end="")
                elif "executed in" in line:
                    print(Fore.GREEN + "    " + line, end="")
                elif "Compression summary:" in line:
                    print(Fore.CYAN + Style.BRIGHT + "    " + line, end="")
                elif "CompressionFormat" in line:
                    print(Fore.MAGENTA + "    " + line, end="")
                elif "Display:" in line:
                    # Skip verbose display lines
                    if any(
                        skip in line
                        for skip in [
                            "Loading",
                            "Using command",
                            "Latency",
                            "PrimaryIndex",
                            "PathHashIndex",
                            "FullDirectoryIndex",
                        ]
                    ):
                        continue
                    print(Fore.CYAN + "    " + line, end="")
                else:
                    if line_stripped:  # Skip empty lines
                        print("    " + line, end="")

        process.wait()

        if process.returncode != 0:
            print(
                Fore.RED
                + f"\n  - Error: UnrealPak exited with code {process.returncode}"
            )
            sys.exit(1)

        return pak_output

    except Exception as e:
        print(Fore.RED + f"  - Error running UnrealPak: {e}")
        sys.exit(1)


def _apply_override(override: Dict[str, str], target_dir: Path, context: str):
    """Apply an override by copying files from source to target."""
    source_path = Path(override["source"])
    description = override.get("description", "Override files")

    if not source_path.is_dir():
        print(
            Fore.YELLOW
            + f"  - Skipping override for '{context}': {source_path} not found"
        )
        return

    print(Fore.CYAN + f"  - Applying override: {description}")
    shutil.copytree(source_path, target_dir, dirs_exist_ok=True)
    file_count = sum(1 for _ in source_path.rglob("*") if _.is_file())
    print(Fore.GREEN + f"    ✓ Merged {file_count} file(s) from {source_path.name}/")


def main():
    parser = argparse.ArgumentParser(
        description="A unified, preset-based build system for DRG mods."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add the edit command
    subparsers.add_parser(
        "edit", help="Open the build_presets.yaml file in your default editor"
    )

    cook_parser = subparsers.add_parser(
        "cook",
        help="Cooks assets. No args runs default cook. Provide preset names for specific cooks.",
    )
    cook_parser.add_argument(
        "presets",
        nargs="*",
        help="Optional: Specific preset names to cook if they have a 'cook_override'.",
    )
    pack_parser = subparsers.add_parser(
        "pack", help="Packs staged assets into .pak files based on presets."
    )
    pack_parser.add_argument(
        "presets",
        nargs="*",
        help="Optional: Specific preset names to pack. If not provided, all enabled presets will be packed.",
    )
    args = parser.parse_args()
    config = load_config()

    if args.command == "edit":
        open_presets_in_editor()
    elif args.command == "cook":
        cook_assets(config, args.presets)
    elif args.command == "pack":
        pack_assets(config, args.presets)


if __name__ == "__main__":
    main()
