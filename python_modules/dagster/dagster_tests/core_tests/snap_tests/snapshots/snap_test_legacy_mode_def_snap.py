# -*- coding: utf-8 -*-
# snapshottest: v1 - https://goo.gl/zC4yUc
from __future__ import unicode_literals

from snapshottest import Snapshot


snapshots = Snapshot()

snapshots['test_mode_snap 1'] = '{"__class__": "ModeDefSnap", "description": null, "logger_def_snaps": [{"__class__": "LoggerDefSnap", "config_field_snap": {"__class__": "ConfigFieldSnap", "default_provided": false, "default_value_as_json_str": null, "description": null, "is_required": false, "name": "config", "type_key": "Any"}, "description": "logger_description", "name": "no_config_logger"}, {"__class__": "LoggerDefSnap", "config_field_snap": {"__class__": "ConfigFieldSnap", "default_provided": false, "default_value_as_json_str": null, "description": null, "is_required": true, "name": "config", "type_key": "Shape.6930c1ab2255db7c39e92b59c53bab16a55f80c1"}, "description": null, "name": "some_logger"}], "name": "default", "resource_def_snaps": [{"__class__": "ResourceDefSnap", "config_field_snap": {"__class__": "ConfigFieldSnap", "default_provided": false, "default_value_as_json_str": null, "description": null, "is_required": false, "name": "config", "type_key": "Any"}, "description": "Built-in filesystem IO manager that stores and retrieves values using pickling.", "name": "io_manager"}, {"__class__": "ResourceDefSnap", "config_field_snap": {"__class__": "ConfigFieldSnap", "default_provided": false, "default_value_as_json_str": null, "description": null, "is_required": false, "name": "config", "type_key": "Any"}, "description": "resource_description", "name": "no_config_resource"}, {"__class__": "ResourceDefSnap", "config_field_snap": {"__class__": "ConfigFieldSnap", "default_provided": false, "default_value_as_json_str": null, "description": null, "is_required": true, "name": "config", "type_key": "Shape.4384fce472621a1d43c54ff7e52b02891791103f"}, "description": null, "name": "some_resource"}], "root_config_key": "Shape.24b4f821010097757feb6562b1babbd10f75499c"}'
