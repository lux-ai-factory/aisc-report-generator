"""The report renderer: a layout snapshot in, one HTML or PDF document out.

Each block of the snapshot is rendered by the renderer registered for its type, in list order,
with the data of the pinned system version only.
"""
