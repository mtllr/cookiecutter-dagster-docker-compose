# -*- coding: utf-8 -*-
# snapshottest: v1 - https://goo.gl/zC4yUc
from __future__ import unicode_literals

from snapshottest import Snapshot


snapshots = Snapshot()

snapshots['test_create_execution_plan_with_dep 1'] = '''{
  "__class__": "ExecutionPlanSnapshot",
  "artifacts_persisted": true,
  "executor_name": "multi_or_in_process_executor",
  "initial_known_state": {
    "__class__": "KnownExecutionState",
    "dynamic_mappings": {},
    "parent_state": null,
    "previous_retry_attempts": {},
    "ready_outputs": {
      "__frozenset__": []
    },
    "step_output_versions": []
  },
  "pipeline_snapshot_id": "ee8de04ca32fa0656a0c040f0e503a5851dc8b8c",
  "snapshot_version": 1,
  "step_keys_to_execute": [
    "op_one",
    "op_two"
  ],
  "steps": [
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [],
      "key": "op_one",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Any",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "op_one",
            "parent": null
          }
        }
      ],
      "solid_handle_id": "op_one",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "op_one",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "op_one",
          "parent": null
        }
      },
      "tags": {}
    },
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [
        {
          "__class__": "ExecutionStepInputSnap",
          "dagster_type_key": "Any",
          "name": "num",
          "source": {
            "__class__": "FromStepOutput",
            "fan_in": false,
            "input_name": "",
            "solid_handle": {
              "__class__": "SolidHandle",
              "name": "",
              "parent": null
            },
            "step_output_handle": {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "result",
              "step_key": "op_one"
            }
          },
          "upstream_output_handles": [
            {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "result",
              "step_key": "op_one"
            }
          ]
        }
      ],
      "key": "op_two",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Any",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "op_two",
            "parent": null
          }
        }
      ],
      "solid_handle_id": "op_two",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "op_two",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "op_two",
          "parent": null
        }
      },
      "tags": {}
    }
  ]
}'''

snapshots['test_create_noop_execution_plan 1'] = '''{
  "__class__": "ExecutionPlanSnapshot",
  "artifacts_persisted": true,
  "executor_name": "multi_or_in_process_executor",
  "initial_known_state": {
    "__class__": "KnownExecutionState",
    "dynamic_mappings": {},
    "parent_state": null,
    "previous_retry_attempts": {},
    "ready_outputs": {
      "__frozenset__": []
    },
    "step_output_versions": []
  },
  "pipeline_snapshot_id": "0b967d368d23e3e2d71555cf3afa343548a291fd",
  "snapshot_version": 1,
  "step_keys_to_execute": [
    "noop_op"
  ],
  "steps": [
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [],
      "key": "noop_op",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Any",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "noop_op",
            "parent": null
          }
        }
      ],
      "solid_handle_id": "noop_op",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "noop_op",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "noop_op",
          "parent": null
        }
      },
      "tags": {}
    }
  ]
}'''

snapshots['test_create_noop_execution_plan_with_tags 1'] = '''{
  "__class__": "ExecutionPlanSnapshot",
  "artifacts_persisted": true,
  "executor_name": "multi_or_in_process_executor",
  "initial_known_state": {
    "__class__": "KnownExecutionState",
    "dynamic_mappings": {},
    "parent_state": null,
    "previous_retry_attempts": {},
    "ready_outputs": {
      "__frozenset__": []
    },
    "step_output_versions": []
  },
  "pipeline_snapshot_id": "25ab027dd42414ee540dfba3020f90ff4c0c6196",
  "snapshot_version": 1,
  "step_keys_to_execute": [
    "noop_op"
  ],
  "steps": [
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [],
      "key": "noop_op",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [
        {
          "__class__": "ExecutionPlanMetadataItemSnap",
          "key": "bar",
          "value": "baaz"
        },
        {
          "__class__": "ExecutionPlanMetadataItemSnap",
          "key": "foo",
          "value": "bar"
        }
      ],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Any",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "noop_op",
            "parent": null
          }
        }
      ],
      "solid_handle_id": "noop_op",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "noop_op",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "noop_op",
          "parent": null
        }
      },
      "tags": {
        "bar": "baaz",
        "foo": "bar"
      }
    }
  ]
}'''

snapshots['test_create_with_graph 1'] = '''{
  "__class__": "ExecutionPlanSnapshot",
  "artifacts_persisted": true,
  "executor_name": "multi_or_in_process_executor",
  "initial_known_state": {
    "__class__": "KnownExecutionState",
    "dynamic_mappings": {},
    "parent_state": null,
    "previous_retry_attempts": {},
    "ready_outputs": {
      "__frozenset__": []
    },
    "step_output_versions": []
  },
  "pipeline_snapshot_id": "10446802a7b75c5c4da33361665a159f9a70215b",
  "snapshot_version": 1,
  "step_keys_to_execute": [
    "comp_1.return_one",
    "comp_1.add_one",
    "comp_2.return_one",
    "comp_2.add_one",
    "add"
  ],
  "steps": [
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [
        {
          "__class__": "ExecutionStepInputSnap",
          "dagster_type_key": "Any",
          "name": "num_one",
          "source": {
            "__class__": "FromStepOutput",
            "fan_in": false,
            "input_name": "",
            "solid_handle": {
              "__class__": "SolidHandle",
              "name": "",
              "parent": null
            },
            "step_output_handle": {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "result",
              "step_key": "comp_1.add_one"
            }
          },
          "upstream_output_handles": [
            {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "result",
              "step_key": "comp_1.add_one"
            }
          ]
        },
        {
          "__class__": "ExecutionStepInputSnap",
          "dagster_type_key": "Any",
          "name": "num_two",
          "source": {
            "__class__": "FromStepOutput",
            "fan_in": false,
            "input_name": "",
            "solid_handle": {
              "__class__": "SolidHandle",
              "name": "",
              "parent": null
            },
            "step_output_handle": {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "result",
              "step_key": "comp_2.add_one"
            }
          },
          "upstream_output_handles": [
            {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "result",
              "step_key": "comp_2.add_one"
            }
          ]
        }
      ],
      "key": "add",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Any",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "add",
            "parent": null
          }
        }
      ],
      "solid_handle_id": "add",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "add",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "add",
          "parent": null
        }
      },
      "tags": {}
    },
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [
        {
          "__class__": "ExecutionStepInputSnap",
          "dagster_type_key": "Int",
          "name": "num",
          "source": {
            "__class__": "FromStepOutput",
            "fan_in": false,
            "input_name": "",
            "solid_handle": {
              "__class__": "SolidHandle",
              "name": "",
              "parent": null
            },
            "step_output_handle": {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "out_num",
              "step_key": "comp_1.return_one"
            }
          },
          "upstream_output_handles": [
            {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "out_num",
              "step_key": "comp_1.return_one"
            }
          ]
        }
      ],
      "key": "comp_1.add_one",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Int",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "add_one",
            "parent": {
              "__class__": "SolidHandle",
              "name": "comp_1",
              "parent": null
            }
          }
        }
      ],
      "solid_handle_id": "comp_1.add_one",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "comp_1.add_one",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "add_one",
          "parent": {
            "__class__": "SolidHandle",
            "name": "comp_1",
            "parent": null
          }
        }
      },
      "tags": {}
    },
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [],
      "key": "comp_1.return_one",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Int",
          "name": "out_num",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "return_one",
            "parent": {
              "__class__": "SolidHandle",
              "name": "comp_1",
              "parent": null
            }
          }
        }
      ],
      "solid_handle_id": "comp_1.return_one",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "comp_1.return_one",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "return_one",
          "parent": {
            "__class__": "SolidHandle",
            "name": "comp_1",
            "parent": null
          }
        }
      },
      "tags": {}
    },
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [
        {
          "__class__": "ExecutionStepInputSnap",
          "dagster_type_key": "Int",
          "name": "num",
          "source": {
            "__class__": "FromStepOutput",
            "fan_in": false,
            "input_name": "",
            "solid_handle": {
              "__class__": "SolidHandle",
              "name": "",
              "parent": null
            },
            "step_output_handle": {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "out_num",
              "step_key": "comp_2.return_one"
            }
          },
          "upstream_output_handles": [
            {
              "__class__": "StepOutputHandle",
              "mapping_key": null,
              "output_name": "out_num",
              "step_key": "comp_2.return_one"
            }
          ]
        }
      ],
      "key": "comp_2.add_one",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Int",
          "name": "result",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "add_one",
            "parent": {
              "__class__": "SolidHandle",
              "name": "comp_2",
              "parent": null
            }
          }
        }
      ],
      "solid_handle_id": "comp_2.add_one",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "comp_2.add_one",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "add_one",
          "parent": {
            "__class__": "SolidHandle",
            "name": "comp_2",
            "parent": null
          }
        }
      },
      "tags": {}
    },
    {
      "__class__": "ExecutionStepSnap",
      "inputs": [],
      "key": "comp_2.return_one",
      "kind": {
        "__enum__": "StepKind.COMPUTE"
      },
      "metadata_items": [],
      "outputs": [
        {
          "__class__": "ExecutionStepOutputSnap",
          "dagster_type_key": "Int",
          "name": "out_num",
          "properties": {
            "__class__": "StepOutputProperties",
            "asset_key": null,
            "is_asset": false,
            "is_asset_partitioned": false,
            "is_dynamic": false,
            "is_required": true,
            "should_materialize": false
          },
          "solid_handle": {
            "__class__": "SolidHandle",
            "name": "return_one",
            "parent": {
              "__class__": "SolidHandle",
              "name": "comp_2",
              "parent": null
            }
          }
        }
      ],
      "solid_handle_id": "comp_2.return_one",
      "step_handle": {
        "__class__": "StepHandle",
        "key": "comp_2.return_one",
        "solid_handle": {
          "__class__": "SolidHandle",
          "name": "return_one",
          "parent": {
            "__class__": "SolidHandle",
            "name": "comp_2",
            "parent": null
          }
        }
      },
      "tags": {}
    }
  ]
}'''
