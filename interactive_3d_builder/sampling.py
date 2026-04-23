from __future__ import annotations

import math


def evenly_spaced_subset(indices: list[int], take: int) -> list[int]:
    if take <= 0:
        return []
    if take >= len(indices):
        return list(indices)

    step = len(indices) / take
    return [indices[min(len(indices) - 1, int(offset * step))] for offset in range(take)]


def stratified_sample_indices(dataset_ids: list[int], side_ids: list[int], max_points: int) -> list[int]:
    total_rows = len(dataset_ids)
    if max_points <= 0 or total_rows <= max_points:
        return list(range(total_rows))

    grouped_indices: dict[tuple[int, int], list[int]] = {}
    for row_index, (dataset_id, side_id) in enumerate(zip(dataset_ids, side_ids)):
        grouped_indices.setdefault((dataset_id, side_id), []).append(row_index)

    quotas: dict[tuple[int, int], int] = {}
    remainders: list[tuple[float, tuple[int, int]]] = []
    used = 0
    for key, group in grouped_indices.items():
        raw_quota = (len(group) * max_points) / total_rows
        base_quota = math.floor(raw_quota)
        quotas[key] = base_quota
        used += base_quota
        remainders.append((raw_quota - base_quota, key))

    remaining = max_points - used
    for _, key in sorted(remainders, key=lambda item: item[0], reverse=True):
        if remaining <= 0:
            break
        if quotas[key] < len(grouped_indices[key]):
            quotas[key] += 1
            remaining -= 1

    sampled_indices: list[int] = []
    for key, group in grouped_indices.items():
        sampled_indices.extend(evenly_spaced_subset(group, quotas[key]))

    sampled_indices.sort()
    return sampled_indices
