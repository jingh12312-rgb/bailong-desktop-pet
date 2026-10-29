"""Screen-safe trajectories and timing, independent of the animation renderer."""
import math
import random


def plan_movement(origin, bounds, size, rng=None, allowed_directions=None, distance_scale=1.0, angle_range=None, downward_angle_range=None):
    """Pick a straight route in either horizontal ±45° cone, within one screen.

    bounds are inclusive allowed top-left coordinates (left, top, right, bottom).
    Never clamp axes independently: that would change the requested direction.
    """
    rng = rng or random
    x, y = origin
    left, top, right, bottom = bounds
    candidates = []
    desired = rng.uniform(size * .65, size * 1.25) * distance_scale
    # Near a side, choose the inward cone rather than a short outward trip.
    edge_margin = size * .65
    directions = (-1, 1)
    if x-left < edge_margin and right-x > x-left: directions = (1,)
    elif right-x < edge_margin and x-left > right-x: directions = (-1,)
    if allowed_directions is not None:
        directions=tuple(d for d in directions if d in allowed_directions)
        if not directions:return None
    angles = (-45, 45)
    if y-top < edge_margin and bottom-y > y-top: angles = (0, 45)
    elif bottom-y < edge_margin and y-top > bottom-y: angles = (-45, 0)
    for _ in range(48):
        direction = rng.choice(directions)
        if angle_range is not None:
            sign=rng.choice((-1,1))
            if angles[0]==0:sign=1
            elif angles[1]==0:sign=-1
            # Leave one degree of room for final integer-pixel positioning.
            limits=downward_angle_range if sign>0 and downward_angle_range else angle_range
            angle=math.radians(sign*rng.uniform(limits[0]+1,limits[1]-1))
        else:angle = math.radians(rng.uniform(*angles))
        dx, dy = direction * math.cos(angle), math.sin(angle)
        limits = [desired]
        if dx > 0: limits.append((right - x) / dx)
        elif dx < 0: limits.append((left - x) / dx)
        if dy > 0: limits.append((bottom - y) / dy)
        elif dy < 0: limits.append((top - y) / dy)
        distance = max(0, min(limits))
        if distance >= min(48, size * .2):
            target = (max(left, min(right, x + dx * distance)),
                      max(top, min(bottom, y + dy * distance)))
            candidates.append((target, direction < 0))
    return rng.choice(candidates) if candidates else None


def movement_fraction(elapsed_ms, start_ms, stop_ms):
    if stop_ms <= start_ms: return 0.0
    return max(0.0, min(1.0, (elapsed_ms - start_ms) / (stop_ms - start_ms)))
