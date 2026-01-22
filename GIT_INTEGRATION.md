# Git Integration Guide

## Overview

The builder now supports git integration with automatic .gitignore generation and simplified commit workflows. The gitignore updater intelligently manages which content folders to ignore and which to track based on your cooking settings and preset asset inclusions.

## Configuration

In `build_presets.yaml`, configure git settings:

```yaml
git_settings:
   # Enable git integration
   enabled: true
   # Generate .gitignore based on cooking settings
   auto_gitignore: true
   # Additional paths to ignore (beyond those from cooking)
   extra_ignores:
      - "staging/"
      - "packaged/"
      - "build_*/"
      - ".vs/"
      - "Intermediate/"
      - "Binaries/"
      - "Saved/"
```

## Commands

### Update .gitignore

Automatically generates `.gitignore` based on your `directories_to_never_cook` and preset asset inclusions:

```bash
python build.py git update-gitignore
```

**What it does:**

- Resolves all paths from `directories_to_never_cook` (including expanded variables and aliases)
- Converts them to Content folder paths and adds ignore patterns
- Analyzes preset `assets.include` patterns to identify what should be tracked
- Automatically negates (with `!`) any ignored paths that are explicitly included in presets
- Adds any `extra_ignores` from git_settings
- **Preserves the existing .gitignore structure** - only replaces the auto-generated section
- Uses `#autogenstart` and `#autogenstop` markers to track auto-generated content
- If markers don't exist, adds the auto-generated section at the end

**Example behavior:**

If your cook settings ignore `Content/_ElytrasMods/` but a preset includes `Content/_ElytrasMods/MyMod/`, the gitignore will have:

```
Content/_ElytrasMods/        # Ignore the whole folder
!Content/_ElytrasMods/MyMod/ # But track this specific subfolder
```

### Add, Commit, Push (ACP)

Stages all changes, commits with a message, and pushes in one command:

```bash
python build.py git acp "Your commit message here"
```

**What it does:**

1. Runs `git add .` (stages all changes)
2. Runs `git commit -m "Your message"` (commits with your message)
3. Runs `git push` (pushes to remote)
4. Shows colored output for each step
5. Handles errors gracefully

**Example:**

```bash
python build.py git acp "Updated cooking settings for EEE preset"
python build.py git acp "Fixed asset compilation errors in CustomDifficulty2"
```

## Workflow Example

1. Make changes to your mod files
2. Update .gitignore if you changed cook settings or presets:

   ```bash
   python build.py git update-gitignore
   ```

3. Commit and push everything at once:

   ```bash
   python build.py git acp "Updated cooking configuration and presets"
   ```

## .gitignore Structure

The tool respects your existing .gitignore structure:

- **Existing content is preserved** - Only the auto-generated section is updated
- **Markers: `#autogenstart` and `#autogenstop`** - Define the auto-generated region
- **Automatic placement** - If no markers exist, adds auto-generated section at the end
- **Original formatting maintained** - Comments, user entries, and structure all preserved

## Features

✓ Auto-generates .gitignore from cook settings and preset inclusions  
✓ Preserves original .gitignore structure and user entries  
✓ Smart ignore/track patterns - tracks included assets even if parent is ignored  
✓ Expands variables and aliases in cook paths  
✓ Uses #autogenstart/#autogenstop markers for easy identification  
✓ Validates git repository exists  
✓ Respects `git_settings.enabled` flag  
✓ Color-coded output for easy readability  
✓ One-command add-commit-push workflow

## Requirements

- Git must be installed and available in PATH
- Current directory must be a git repository (run `git init` if needed)
- `git_settings.enabled` must be `true` in build_presets.yaml
