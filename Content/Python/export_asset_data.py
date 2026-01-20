# pyright: reportPossiblyUnboundVariable=false
# Filename: Content/Python/export_asset_data.py
# Version 15: Fixed malformed output by stripping single quotes from all parsed class paths.

try:
    import unreal # pyright: ignore[reportMissingImports]
except ImportError:
    pass

import json
import sys

def clean_class_name(class_path_str):
    if not class_path_str:
        return "Unknown"
    return class_path_str.split('.')[-1].strip("'")

def get_blueprint_parent_class_from_registry(asset_data):
    try:
        parent_class_path = asset_data.get_tag_value('ParentClass')
        return clean_class_name(parent_class_path)
    except Exception:
        return "Unknown"

def get_material_instance_parent(asset_data):
    try:
        parent_path = asset_data.get_tag_value('Parent')
        return clean_class_name(str(parent_path))
    except Exception:
        return "Unknown"

def get_widget_blueprint_parent(asset_data):
    try:
        parent_class_path = asset_data.get_tag_value('ParentClass')
        if parent_class_path:
            parent_class_name = clean_class_name(parent_class_path)
            return parent_class_name[:-2] if parent_class_name.endswith("_C") else parent_class_name
        return "Unknown"
    except Exception:
        return "Unknown"

def get_blueprint_native_parent_class_from_registry(asset_data):
    try:
        parent_class_path = asset_data.get_tag_value('NativeParentClass')
        return clean_class_name(parent_class_path)
    except Exception:
        return "Unknown"

def get_blueprint_native_class_from_registry(asset_data):
    try:
        parent_class_path = asset_data.get_tag_value('NativeClass')
        return clean_class_name(parent_class_path)
    except Exception:
        return "Unknown"

def get_asset_type(asset_data):
    try:
        asset_class = str(asset_data.asset_class)
        if asset_class == 'Blueprint':
            native_parent = get_blueprint_native_parent_class_from_registry(asset_data)
            if native_parent == 'UserWidget':
                return 'WidgetBlueprint'
            return 'Blueprint'
        if asset_class == 'UserDefinedStruct': return 'Struct'
        if asset_class == 'UserDefinedEnum': return 'Enum'
        if asset_class == 'Material': return 'Material'
        if asset_class == 'MaterialInstanceConstant': return 'MaterialInstance'
        return asset_class
    except Exception:
        return "Unknown"

def main():
    if 'unreal' not in sys.modules:
        print("This script must be run within the Unreal Editor.")
        return
    
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    unreal.log("Waiting for Asset Registry to complete discovery...")
    asset_registry.wait_for_completion()
    unreal.log("Asset Registry discovery complete.")

    filter = unreal.ARFilter(package_paths=["/Game"], recursive_paths=True)
    all_assets = asset_registry.get_assets(filter)
    total_assets = len(all_assets)
    unreal.log(f"Found {total_assets} assets to process from the Asset Registry.")
    
    asset_metadata = {}
    with unreal.ScopedSlowTask(total_assets, "Exporting Asset Metadata...") as slow_task:
        slow_task.make_dialog(True)
        for asset in all_assets:
            if slow_task.should_cancel(): break
            slow_task.enter_progress_frame(1)
            
            # The order here is important, get_asset_type may rely on other functions
            asset_type = get_asset_type(asset)
            parent = "Unknown"
            native_parent = get_blueprint_native_parent_class_from_registry(asset)
            native_class = get_blueprint_native_class_from_registry(asset)

            if asset_type == 'Blueprint':
                parent = get_blueprint_parent_class_from_registry(asset)
            elif asset_type == 'WidgetBlueprint':
                parent = get_widget_blueprint_parent(asset)
            elif asset_type == 'MaterialInstance':
                parent = get_material_instance_parent(asset)
            
            data = {
                "asset_type": asset_type,
                "parent_class": parent,
                "native_parent_class": native_parent,
                "native_class": native_class
            }
            
            asset_metadata[str(asset.package_name)] = data
    
    output_path = unreal.Paths.project_dir() + "asset_data.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(asset_metadata, f, indent=4)
        
    unreal.log(f"Successfully exported metadata for {len(asset_metadata)} assets to {output_path}")

if __name__ == "__main__":
    main()