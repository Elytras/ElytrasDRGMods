import unreal
import os


def rename_assets_in_folder(folder_path, search_string, replace_string, recursive=True):
    """
    Renames assets in a specific folder by replacing a substring in their name.

    :param folder_path: The content path to search (e.g., "/Game/MyFolder")
    :param search_string: The string to look for in the asset name
    :param replace_string: The string to replace it with
    :param recursive: Whether to search inside sub-folders
    """

    # 1. Get the Editor Asset Library
    editor_asset_lib = unreal.EditorAssetLibrary()

    # 2. List all assets in the specified directory
    # recursive=True will get assets in subfolders
    # include_folder=False ensures we only get files, not folder directories
    assets = editor_asset_lib.list_assets(
        folder_path, recursive=recursive, include_folder=False
    )

    count = 0

    with unreal.ScopedEditorTransaction("Batch Rename Assets"):
        try:
            for asset_path in assets:
                # asset_path looks like: "/Game/MyFolder/SM_OldName.SM_OldName"

                # 3. Parse the path to get the folder and the asset name separately
                # We use standard string manipulation.
                # package_name is "/Game/MyFolder/SM_OldName"
                package_name = asset_path.split(".")[0]
                directory = os.path.dirname(package_name)  # "/Game/MyFolder"
                old_asset_name = os.path.basename(package_name)  # "SM_OldName"

                # 4. Check if the search string is in the asset name
                if search_string in old_asset_name:

                    # 5. Create the new name
                    new_asset_name = old_asset_name.replace(
                        search_string, replace_string
                    )

                    # 6. Construct the full new path
                    # New path must constitute: /Game/Folder/NewName.NewName
                    # But rename_asset expects just the package path: /Game/Folder/NewName
                    new_package_path = "{}/{}".format(directory, new_asset_name)

                    # 7. Perform the rename
                    # rename_asset handles the move and referencing
                    success = editor_asset_lib.rename_asset(
                        package_name, new_package_path
                    )

                    if success:
                        unreal.log(
                            "Renamed: {} -> {}".format(old_asset_name, new_asset_name)
                        )
                        count += 1
                    else:
                        unreal.log_error("Failed to rename: {}".format(asset_path))
        except Exception as e:
            unreal.log(f"The error message is: {e}")

    unreal.log("Completed. Renamed {} assets.".format(count))


# --- HOW TO RUN ---
# Change these values to match your needs
target_folder = "/Game/_ElytrasMods/ModManager/Widgets/Main/UI"
find_text = "WUnifiedUI"
replace_text = "WBP_EMM"

rename_assets_in_folder(target_folder, find_text, replace_text)
