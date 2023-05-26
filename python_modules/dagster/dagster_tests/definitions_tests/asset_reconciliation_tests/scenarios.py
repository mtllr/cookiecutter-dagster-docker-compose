from dagster import Definitions
from dagster._core.definitions.executor_definition import in_process_executor

from .active_run_scenarios import active_run_scenarios
from .auto_materialize_policy_scenarios import auto_materialize_policy_scenarios
from .basic_scenarios import basic_scenarios
from .definition_change_scenarios import definition_change_scenarios
from .exotic_partition_mapping_scenarios import exotic_partition_mapping_scenarios
from .freshness_policy_scenarios import freshness_policy_scenarios
from .multi_code_location_scenarios import multi_code_location_scenarios
from .observable_source_asset_scenarios import observable_source_asset_scenarios
from .partition_scenarios import partition_scenarios

ASSET_RECONCILIATION_SCENARIOS = {
    **exotic_partition_mapping_scenarios,
    **partition_scenarios,
    **basic_scenarios,
    **freshness_policy_scenarios,
    **auto_materialize_policy_scenarios,
    **observable_source_asset_scenarios,
    **definition_change_scenarios,
    **active_run_scenarios,
}

# put repos in the global namespace so that the daemon can load them with LoadableTargetOrigin
for scenario_name, scenario in ASSET_RECONCILIATION_SCENARIOS.items():
    assert scenario.assets is not None and scenario.code_locations is None
    d = Definitions(assets=scenario.assets, executor=in_process_executor)
    globals()["hacky_daemon_repo_" + scenario_name] = d.get_repository_def()

for scenario_name, scenario in multi_code_location_scenarios.items():
    assert scenario.assets is None and scenario.code_locations is not None
    for location_name, assets in scenario.code_locations.items():
        d = Definitions(assets=assets, executor=in_process_executor)
        globals()[
            "hacky_daemon_repo_" + scenario_name + "_" + location_name
        ] = d.get_repository_def()
