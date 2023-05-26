from datetime import datetime
from typing import NamedTuple, Optional, cast

import dagster._check as check
from dagster._annotations import PublicAttr
from dagster._core.definitions.partition import PartitionsDefinition, PartitionsSubset
from dagster._core.definitions.partition_key_range import PartitionKeyRange
from dagster._core.definitions.partition_mapping import PartitionMapping
from dagster._core.definitions.time_window_partitions import (
    TimeWindow,
    TimeWindowPartitionsDefinition,
    TimeWindowPartitionsSubset,
)
from dagster._core.errors import DagsterInvalidDefinitionError, DagsterInvalidInvocationError
from dagster._core.instance import DynamicPartitionsStore
from dagster._serdes import whitelist_for_serdes


@whitelist_for_serdes
class TimeWindowPartitionMapping(
    PartitionMapping,
    NamedTuple(
        "_TimeWindowPartitionMapping",
        [("start_offset", PublicAttr[int]), ("end_offset", PublicAttr[int])],
    ),
):
    """The default mapping between two TimeWindowPartitionsDefinitions.

    A partition in the downstream partitions definition is mapped to all partitions in the upstream
    asset whose time windows overlap it.

    This means that, if the upstream and downstream partitions definitions share the same time
    period, then this mapping is essentially the identity partition mapping - plus conversion of
    datetime formats.

    If the upstream time period is coarser than the downstream time period, then each partition in
    the downstream asset will map to a single (larger) upstream partition. E.g. if the downstream is
    hourly and the upstream is daily, then each hourly partition in the downstream will map to the
    daily partition in the upstream that contains that hour.

    If the upstream time period is finer than the downstream time period, then each partition in the
    downstream asset will map to multiple upstream partitions. E.g. if the downstream is daily and
    the upstream is hourly, then each daily partition in the downstream asset will map to the 24
    hourly partitions in the upstream that occur on that day.

    Attributes:
        start_offset (int): If not 0, then the starts of the upstream windows are shifted by this
            offset relative to the starts of the downstream windows. For example, if start_offset=-1
            and end_offset=0, then the downstream partition "2022-07-04" would map to the upstream
            partitions "2022-07-03" and "2022-07-04". Only permitted to be non-zero when the
            upstream and downstream PartitionsDefinitions are the same. Defaults to 0.
        end_offset (int): If not 0, then the ends of the upstream windows are shifted by this
            offset relative to the ends of the downstream windows. For example, if start_offset=0
            and end_offset=1, then the downstream partition "2022-07-04" would map to the upstream
            partitions "2022-07-04" and "2022-07-05". Only permitted to be non-zero when the
            upstream and downstream PartitionsDefinitions are the same. Defaults to 0.

    Examples:
        .. code-block:: python

            from dagster import DailyPartitionsDefinition, TimeWindowPartitionMapping, AssetIn, asset

            partitions_def = DailyPartitionsDefinition(start_date="2020-01-01")

            @asset(partitions_def=partitions_def)
            def asset1():
                ...

            @asset(
                partitions_def=partitions_def,
                ins={
                    "asset1": AssetIn(
                        partition_mapping=TimeWindowPartitionMapping(start_offset=-1)
                    )
                }
            )
            def asset2(asset1):
                ...
    """

    def __new__(cls, start_offset: int = 0, end_offset: int = 0):
        return super(TimeWindowPartitionMapping, cls).__new__(
            cls,
            start_offset=check.int_param(start_offset, "start_offset"),
            end_offset=check.int_param(end_offset, "end_offset"),
        )

    def get_upstream_partitions_for_partition_range(
        self,
        downstream_partition_key_range: Optional[PartitionKeyRange],
        downstream_partitions_def: Optional[PartitionsDefinition],
        upstream_partitions_def: PartitionsDefinition,
    ) -> PartitionKeyRange:
        raise NotImplementedError()

    def get_upstream_partitions_for_partitions(
        self,
        downstream_partitions_subset: Optional[PartitionsSubset],
        upstream_partitions_def: PartitionsDefinition,
        current_time: Optional[datetime] = None,
        dynamic_partitions_store: Optional[DynamicPartitionsStore] = None,
    ) -> PartitionsSubset:
        """Returns the partitions in the upstream asset that map to the given downstream partitions.

        Raises an error if upstream partitions do not exist at the given current_time, fetching the
        current time if not provided.
        """
        if not isinstance(downstream_partitions_subset, TimeWindowPartitionsSubset):
            check.failed("downstream_partitions_subset must be a TimeWindowPartitionsSubset")

        if not isinstance(upstream_partitions_def, TimeWindowPartitionsDefinition):
            check.failed("upstream_partitions_def must be a TimeWindowPartitionsDefinition")

        return self._map_partitions(
            cast(TimeWindowPartitionsDefinition, downstream_partitions_subset.partitions_def),
            upstream_partitions_def,
            downstream_partitions_subset,
            self.start_offset,
            self.end_offset,
            raise_on_non_existent_partition=True,
            current_time=current_time,
        )

    def get_downstream_partitions_for_partition_range(
        self,
        upstream_partition_key_range: PartitionKeyRange,
        downstream_partitions_def: Optional[PartitionsDefinition],
        upstream_partitions_def: PartitionsDefinition,
    ) -> PartitionKeyRange:
        raise NotImplementedError()

    def get_downstream_partitions_for_partitions(
        self,
        upstream_partitions_subset: PartitionsSubset,
        downstream_partitions_def: Optional[PartitionsDefinition],
        current_time: Optional[datetime] = None,
        dynamic_partitions_store: Optional[DynamicPartitionsStore] = None,
    ) -> PartitionsSubset:
        """Returns the partitions in the downstream asset that map to the given upstream partitions.

        Filters for partitions that exist at the given current_time, fetching the current time
        if not provided.
        """
        if not isinstance(downstream_partitions_def, TimeWindowPartitionsDefinition):
            check.failed("downstream_partitions_def must be a TimeWindowPartitionsDefinitions")

        if not isinstance(upstream_partitions_subset, TimeWindowPartitionsSubset):
            check.failed("upstream_partitions_subset must be a TimeWindowPartitionsSubset")

        return self._map_partitions(
            cast(TimeWindowPartitionsDefinition, upstream_partitions_subset.partitions_def),
            downstream_partitions_def,
            upstream_partitions_subset,
            -self.start_offset,
            -self.end_offset,
            raise_on_non_existent_partition=False,
            current_time=current_time,
        )

    def _map_partitions(
        self,
        from_partitions_def: TimeWindowPartitionsDefinition,
        to_partitions_def: TimeWindowPartitionsDefinition,
        from_partitions_subset: TimeWindowPartitionsSubset,
        start_offset: int,
        end_offset: int,
        raise_on_non_existent_partition: bool,
        current_time: Optional[datetime] = None,
    ) -> TimeWindowPartitionsSubset:
        if (start_offset != 0 or end_offset != 0) and (
            from_partitions_def.cron_schedule != to_partitions_def.cron_schedule
        ):
            raise DagsterInvalidDefinitionError(
                "Can't use the start_offset or end_offset parameters of"
                " TimeWindowPartitionMapping when the cron schedule of the upstream"
                " PartitionsDefinition is different than the cron schedule of the downstream"
                f" one. Attempted to map from cron schedule '{from_partitions_def.cron_schedule}' "
                f"to cron schedule '{to_partitions_def.cron_schedule}'."
            )

        if to_partitions_def.timezone != from_partitions_def.timezone:
            raise DagsterInvalidDefinitionError("Timezones don't match")

        # skip fancy mapping logic in the simple case
        if from_partitions_def == to_partitions_def and start_offset == 0 and end_offset == 0:
            return from_partitions_subset

        time_windows = []
        for from_partition_time_window in from_partitions_subset.included_time_windows:
            from_start_dt, from_end_dt = from_partition_time_window
            offsetted_start_dt = _offsetted_datetime(
                from_partitions_def, from_start_dt, start_offset
            )
            offsetted_end_dt = _offsetted_datetime(from_partitions_def, from_end_dt, end_offset)

            to_start_partition_key = (
                to_partitions_def.get_partition_key_for_timestamp(
                    offsetted_start_dt.timestamp(), end_closed=False
                )
                if offsetted_start_dt is not None
                else None
            )
            to_end_partition_key = (
                to_partitions_def.get_partition_key_for_timestamp(
                    offsetted_end_dt.timestamp(), end_closed=True
                )
                if offsetted_end_dt is not None
                else None
            )

            if to_start_partition_key is not None or to_end_partition_key is not None:
                window_start = (
                    to_partitions_def.start_time_for_partition_key(to_start_partition_key)
                    if to_start_partition_key
                    else cast(TimeWindow, to_partitions_def.get_first_partition_window()).start
                )
                window_end = (
                    to_partitions_def.end_time_for_partition_key(to_end_partition_key)
                    if to_end_partition_key
                    else cast(TimeWindow, to_partitions_def.get_last_partition_window()).end
                )

                if window_start < window_end:
                    time_windows.append(TimeWindow(window_start, window_end))

        first_window = to_partitions_def.get_first_partition_window(current_time=current_time)
        last_window = to_partitions_def.get_last_partition_window(current_time=current_time)

        filtered_time_windows = []

        for time_window in time_windows:
            if (
                first_window
                and last_window
                and time_window.start <= last_window.start
                and time_window.end >= first_window.end
            ):
                window_end = min(time_window.end, last_window.end)
                window_start = max(time_window.start, first_window.start)
                filtered_time_windows.append(TimeWindow(window_start, window_end))

        if raise_on_non_existent_partition:
            if filtered_time_windows != time_windows:
                raise DagsterInvalidInvocationError(
                    f"Provided time windows {time_windows} contain invalid time windows for"
                    f" partitions definition {to_partitions_def}"
                )

        return TimeWindowPartitionsSubset(
            to_partitions_def,
            num_partitions=sum(
                len(to_partitions_def.get_partition_keys_in_time_window(time_window))
                for time_window in filtered_time_windows
            ),
            included_time_windows=filtered_time_windows,
        )


def _offsetted_datetime(
    partitions_def: TimeWindowPartitionsDefinition, dt: datetime, offset: int
) -> Optional[datetime]:
    for _ in range(abs(offset)):
        if offset < 0:
            prev_window = partitions_def.get_prev_partition_window(dt)
            if prev_window is None:
                return None

            dt = prev_window.start
        else:
            # TODO: what if we're at the end of the line?
            next_window = partitions_def.get_next_partition_window(dt)
            if next_window is None:
                return None

            dt = next_window.end

    return dt
