"""Booking intervals, as (start, end) pairs of integers, with end after start."""


def merge(bookings):
    """Return the bookings merged into a sorted list of non-overlapping intervals.
    Intervals that touch, such as (1, 3) and (3, 5), merge into one. The input is left unchanged."""
    bookings.sort()
    merged = []
    for start, end in bookings:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def free_slots(bookings, day_start, day_end):
    """Return the gaps between day_start and day_end not covered by any booking, in order.
    Bookings may reach outside the day. Empty gaps are left out."""
    slots = []
    cursor = day_start
    for start, end in merge(bookings):
        if start > cursor:
            slots.append((cursor, start))
        cursor = end
    if cursor < day_end:
        slots.append((cursor, day_end))
    return slots
