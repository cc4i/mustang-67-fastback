"""Body details (windows, louvers, side scoop, lamp and grille pockets, peg holes)
and the parts that fit into them (grille, lamp lenses, bumpers).

Outlines are in real-car millimetres; offsets and clearances in print millimetres.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import features as F
from body import CORNER_EXT, SCALE

FIT = 0.12                # clearance per side for inserts in pockets (print mm)
PEG_R, PEG_HOLE_R = 0.75, 0.9
PEG_LEN = 3.0

# ---------------------------------------------------------------- outlines

# side glass (side view): from the A-pillar's rear edge back to the quarter glass at QUARTER_X1,
# under the roof rail and along the sill. The A-pillar is a slim post: its rear edge (which the vent
# window's front edge follows) is a straight line ~75 mm behind and parallel to the windshield's side
# edge. The rail runs RAIL_MARGIN under the roof edge, and level forward of RAIL_X_FLAT, where the
# model's roof edge drops away toward the windshield; it sweeps into the pillar on a radius of ~80 mm
# (OPEN_CORNER_T: the fillet's tangent length on that 135 degree corner).
A_PILLAR = ((1780.0, 918.0), (2110.0, 1248.0))   # two points on the A-pillar's rear edge, below the sill and above the rail
RAIL_MARGIN, RAIL_X_FLAT = 30.0, 2150.0
OPEN_CORNER_T = 33.0
DRIP_RAIL = (6.0, 18.0, 0.2)        # chrome drip moulding over the opening and down the pillar: offsets out (real), proud (print mm)
OPENING_STEPS = 6                   # points per fillet of the opening's outline (each fillet becomes steps + 1 points)
QUARTER_X1 = 2887.0


def greenhouse_band(x, sill_margin=14.0, top_margin=14.0):
    """(sill z, roof-edge z) of the greenhouse side at station x, inset by margins (real mm)."""
    from body import section
    pts = section(x)
    return pts[10][1] + sill_margin, pts[12][1] - top_margin


def sill_z(x):
    """Bottom of the side window opening (the window sill line) at station x."""
    return greenhouse_band(x)[0]


def rail_z(x):
    """Top of the side window opening (the underside of the roof rail) at station x."""
    return greenhouse_band(max(x, RAIL_X_FLAT), top_margin=RAIL_MARGIN)[1]


def pillar_point(t, behind=0.0):
    """Point t on the A-pillar's rear edge in the side view (t = 0, 1: the A_PILLAR points), or on
    the parallel line `behind` real mm behind it."""
    p0, p1 = Vector(A_PILLAR[0]), Vector(A_PILLAR[1])
    d = (p1 - p0).normalized()
    return p0.lerp(p1, t) + Vector((d.y, -d.x)) * behind


def pillar_meets(line_z, behind=0.0):
    """Where the A-pillar's rear edge (or a parallel `behind` it) meets a height line z = line_z(x)."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        p = pillar_point(mid, behind)
        lo, hi = (mid, hi) if p.y < line_z(p.x) else (lo, mid)
    return pillar_point((lo + hi) / 2, behind)


def rail_over(x):
    """Top of the side window opening at station x where the roof rail (or the top of its corner
    into the pillar) forms it; -inf elsewhere."""
    if not OPEN_CORNER_X - OPEN_CORNER_T <= x <= QUARTER_X1:
        return -math.inf
    tops = []
    for (x0, z0), (x1, z1) in zip(WINDOW_OPEN, WINDOW_OPEN[1:] + WINDOW_OPEN[:1]):
        if min(x0, x1) <= x <= max(x0, x1) and x0 != x1:
            tops.append(z0 + (z1 - z0) * (x - x0) / (x1 - x0))
    return max(tops)


def side_opening(samples=14, steps=OPENING_STEPS):
    """The side window opening, glass wound down: from the A-pillar's rear edge (the vent window,
    which rides on the door, has gone with it) back to the quarter glass, under the roof rail, and
    along the sill line, sampled so the door's top edge, which follows the same line, meets it
    everywhere. Returns the outline and how many of its points form the upper run, from the pillar's
    foot up the pillar and along the rail to its rear corner."""
    p0, c = pillar_meets(sill_z), pillar_meets(rail_z)
    # (the first rail sample stands far enough back for the corner fillet's full tangent: rounded_poly
    # clamps it to half the shorter edge)
    first = 2.1 * OPEN_CORNER_T
    xs = [c.x + first + (QUARTER_X1 - c.x - first) * k / (samples - 1) for k in range(samples)]
    pts = [tuple(p0), tuple(c)] + [(x, rail_z(x)) for x in xs]
    pts.append((QUARTER_X1, sill_z(QUARTER_X1)))
    pts += [(x, sill_z(x)) for x in (QUARTER_X1 + (p0.x - QUARTER_X1) * k / samples for k in range(1, samples))]
    radii = [15.0, OPEN_CORNER_T] + [0.0] * (samples - 1) + [40.0, 15.0] + [0.0] * (samples - 1)
    upper = sum(steps + 1 if r > 0 else 1 for r in radii[:samples + 2])      # each fillet becomes steps + 1 points
    return F.rounded_poly(pts, radii, steps), upper


WINDOW_OPEN, WINDOW_OPEN_UPPER = side_opening()
OPEN_CORNER_X = pillar_meets(rail_z).x          # the opening's top front corner
# print mm: through the wall into the cabin everywhere (the inclined A-pillar wall is ~7 mm deep
# along y), well short of anything else inside the opening's outline
WINDOW_CUT_DEPTH = 8.0
BELTLINE_X0, BELTLINE_Y = 1772.0, (600.0, 700.0)   # beltline clearance: from just behind the door's front edge; |y| band
BELTLINE_TOP, BELTLINE_PILLAR = 25.0, 6.0           # it reaches sill + 25 behind the A-pillar, and stays 6 mm behind the pillar
WINDSHIELD = F.rounded_poly([(1712, -590), (2055, -500), (2055, 500), (1712, 590)], 70)

# door shut lines (side view): front and rear edges, from the rocker moulding up toward the sill
# (doors.py cuts the opening doors along them)
DOOR_FRONT = ((1550, 405), (1559, 850))
DOOR_REAR = ((2736, 405), (2797, 880))
DOOR_HANDLE = (2622, 884, 2778, 912)          # x0, z0, x1, z1
DOOR_LOCK = (2700, 848, 15)                   # x, z, r
# trunk-lid gaps: across behind the rear glass, and down each side sweeping outboard along the fins'
# inner edges to the tail's top roll (plan, x, |y|); then on over the roll and down the tail face
# (rear view, |y|, z), leaning out a little as it falls and straight from the last knot down through
# the trim (photo 3). deck_gap_path joins the two
DECKLID_SIDE = [(3865.0, 555.0), (4100.0, 572.0), (4300.0, 622.0), (4420.0, 676.0)]
DECKLID_REAR = [(684.0, 1006.0), (689.0, 992.0), (692.0, 982.0), (692.0, 976.0)]
DECKLID_X0, DECKLID_Y = DECKLID_SIDE[0]
DECKLID_GAP = (13.0, 8.0)                     # groove width (real mm) along the top, and down the tail face
# the quarter extension's joint to the quarter panel (side view, real mm): it keeps EXT_SEAM_BACK ahead of
# the extension's rear face all the way up, so the cap reads as an even-width column, from where the
# extension stands on the bumper up onto its rounded top (ext_seam)
EXT_SEAM_BACK, EXT_SEAM_TOP = 70.0, 1015.0
EXT_SEAM_DEPTH = 0.25                         # print mm: a tight joint, finer than the panel gaps
def _bezier(p0, mid, p1, n):
    """n+1 points on the quadratic arc from p0 to p1 passing through mid."""
    c = (2 * mid[0] - (p0[0] + p1[0]) / 2, 2 * mid[1] - (p0[1] + p1[1]) / 2)
    return [tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t * t * d for a, b, d in zip(p0, c, p1))
            for t in (k / n for k in range(n + 1))]


# the backlight: wide, its top edge arched (higher, so further forward, in the middle) and its base
# bowed a little too, following the roof's crown
_TOP = _bezier((3050, -545), (2900, 0), (3050, 545), 10)
_BASE = _bezier((3850, 510), (3770, 0), (3850, -510), 10)
REAR_GLASS = F.rounded_poly(_TOP + _BASE, [60] + [0] * 9 + [60, 60] + [0] * 9 + [60])
# print mm: the glass faces sit this far below the skin (the backlight shallow, so the chrome
# surround's rear-facing step down to it stays thin from behind); under each face a GLASS_T thick
# inlay fills the bottom of the recess, printed in black as a second part of the body object
GLASS_RECESSES = {"Windshield": (WINDSHIELD, 0.5), "Rear": (REAR_GLASS, 0.3)}
GLASS_T = 0.8

# side sculpture: a cove sweeping back from the front fender into the scoop behind the door
SCOOP_COVE = F.rounded_poly(
    [(2050, 835), (2450, 812), (2850, 780), (3010, 772), (3015, 552), (2850, 560), (2450, 610), (2150, 690)],
    [60, 0, 0, 40, 40, 0, 0, 60])
COVE_START = 2050.0


def cove_fade(u, v):
    """Depth multiplier of the side cove: it fades in from COVE_START toward the scoop."""
    return max(0.0, min(1.0, (u - COVE_START) / 950.0)) ** 1.3
# the intake is split by a horizontal fin, as on the real scoop
SCOOP_INTAKES = [F.rounded_poly([(2822, 676), (2826, 762), (2994, 768), (2998, 674)], 20),
                 F.rounded_poly([(2816, 570), (2820, 640), (2998, 638), (3002, 566)], 20)]

# twin raised hood scoops (mid hood) and the louvered vents at the rear of the hood
HOOD_SCOOPS = [F.rounded_poly([(760, s * 95), (760, s * 430), (1210, s * 400), (1210, s * 110)], [30, 30, 60, 60]) for s in (-1, 1)]
SCOOP_FRONT, SCOOP_REAR, SCOOP_H = 760.0, 1210.0, 0.85


def cowl_louvers():
    """Louver slots at the rear of the hood (part of the opening hood)."""
    slots = []
    for s in (-1, 1):
        for k in range(6):
            y = s * (45 + 38 * k)
            slots.append(rect(1545, y - 10, 1600, y + 10, 6))
    return slots


def hood_scoop_pieces(tree, body_mesh):
    """[(name, solid)] twin raised scoops, built on the original body surface (they ride on the hood)."""
    def scoop(u, v):
        # crisp front edge, flat top, fading into the hood toward the rear and at the sides
        t = (u - SCOOP_FRONT) / (SCOOP_REAR - SCOOP_FRONT)
        inner, outer = 95 + 15 * t, 430 - 30 * t
        rear = max(0.0, min(1.0, (SCOOP_REAR - u) / 260.0))
        side = max(0.0, min(1.0, min(abs(v) - inner, outer - abs(v)) / 20.0))
        return SCOOP_H * rear * side

    return [(f"Hood_Scoop{i}", F.surface_solid(f"Hood_Scoop{i}", body_mesh, "+Z", outline, lambda u, v: -0.4,
                                               lambda u, v: scoop(u, v) - 0.06, rings=8, tree=tree, step=0.4))
            for i, outline in enumerate(HOOD_SCOOPS)]


def hood_louver_cutters(tree, body_mesh):
    return [(f"Hood_LouverCut{i}", F.surface_cutter(f"Hood_LouverCut{i}", body_mesh, "+Z", slot, 0.5, rings=3, tree=tree))
            for i, slot in enumerate(cowl_louvers())]


# front valance parking lamps: small chrome-ringed inserts in pockets square to the raked valance
PARK_LIGHTS = [(s * 640.0, 430.0, 34.0) for s in (-1, 1)]       # y, z, radius
PARK_DEPTH = 1.0                                                  # pocket depth (print mm)
# rear valance: round backup lamps either side of a recessed licence plate. Each is a separate chrome
# housing standing out of a socket in the valance: a cone flaring from a vertical face back into the
# valance (BACKUP_FLARE real mm of radius per mm), so from behind a sliver of its side shows round the
# bezel and from three quarters it reads as a short chrome bucket, as on the car. The flare stops at
# BACKUP_SPIGOT_X, where the valance crosses the lamp's axis, and a straight spigot runs on to the flat
# back, so the housing slides into its round socket from behind the car; round the cone's top, where the
# valance stands further back, the socket's mouth shows as a dark recess, as in photo 3
BACKUP_LIGHTS = [(s * 642.0, 558.0, 37.5) for s in (-1, 1)]     # y, z, bezel radius at the face
BACKUP_FACE_X, BACKUP_BACK_X, BACKUP_FLARE = 4493.0, 4405.0, 0.2
BACKUP_SPIGOT_X = 4450.0
# the face: a rolled chrome bezel ring, its outer edge rounding over (BACKUP_EDGE_R) to a narrow flat crest
# at BACKUP_CREST_R, so it catches light all round as a thin bright ring; inside it falls to a lens
# BACKUP_LENS_R round sunk BACKUP_LENS_DEPTH (print mm) that domes BACKUP_LENS_DOME; the ring's foot is
# 0.5 mm wide printed. The lens is moulded in rings and darkens toward its rim (material)
BACKUP_EDGE_R, BACKUP_CREST_R, BACKUP_LENS_R = 5.0, 31.5, 25.5
BACKUP_LENS_DEPTH, BACKUP_LENS_DOME = 0.35, 0.2
PLATE = (-152.0, 525.0, 152.0, 672.0)          # y0, z0, y1, z1: a 12 x 6 in plate (black recess)
PLATE_DEPTH = 0.6

GRILLE_Y, GRILLE_Z0, GRILLE_Z1, GRILLE_R = 593.0, 552.0, 800.0, 60.0
GRILLE = F.rounded_poly([(-GRILLE_Y, GRILLE_Z0), (GRILLE_Y, GRILLE_Z0), (GRILLE_Y, GRILLE_Z1), (-GRILLE_Y, GRILLE_Z1)], GRILLE_R)
HEADLIGHT_R, HEADLIGHT_Y, HEADLIGHT_Z = 86.0, 715.0, 680.0
HEADLIGHT_FLARE = 12.0     # bucket radius grows by this much from floor to body face
FOG_Y, FOG_R = 440.0, 64.0
# the round lamps are sealed beams: a chrome retaining ring LAMP_RING_W (real mm) wide standing
# LAMP_RING_H (print mm) round a domed lens that rises LAMP_DOME from the ring's foot
LAMP_RING_W, LAMP_RING_H, LAMP_DOME = 12.0, 0.35, 0.4
# tail: a chrome strip frames the panel, along the top edge and down both corners; inside it the
# panel is set back and carries the taillights, gas cap, trunk lock and spaced MUSTANG letters
TRIM_W, TRIM_INSET, TAIL_EDGE_DROP = 14.0, 9.0, 12.0   # strip width; how far inside the face's edge
# the strip runs along the deck lid's raised centre, steps down in a soft S where the deck-lid crease
# meets the tail, runs level across the quarter-extension fins and turns tightly down the corners
TRIM_STEP_Y, TRIM_STEP_LEN, TRIM_CORNER_R = 543.0, 101.0, 18.0
# trim height relative to the deck lid's trailing edge at the centre line (tail_trim_ref): crowned in the
# middle, falling gently to the S, then the outer level
TRIM_CROWN, TRIM_STEP_TOP, TRIM_LOW = 6.5, -2.0, -24.0
# below the letter band the panel is set back under a shadow line, out to where the quarter
# extensions start to stand proud of it (body.CORNER_EXT_Y)
TAIL_RECESS = 0.75                             # print mm
RECESS_HALF, RECESS_TOP = 765.0, 929.0
# three tall lenses per side, each in its own chrome bezel with body colour between: a chrome frame
# round a deep-set red lens, every rail at least 0.5 mm wide once printed (FIT-trimmed), so the
# 0.42 mm line prints it (the body rib between pockets, 85 - 72 mm, can't spare more bezel width)
TAIL_LAMP_Y = (552.5, 637.5, 722.5)            # lamp centres (right side; mirrored on the left)
TAIL_BEZEL_W, TAIL_LENS_W = 72.0, 42.0            # bezel; window (the lens is FIT smaller all round)
TAIL_BAR_Z0, TAIL_BAR_Z1 = 752.0, 912.0        # bezel
TAIL_LENS_Z0, TAIL_LENS_Z1 = 768.0, 896.0
# the lamps are not straight bars but bend at TAIL_BEND of their height: below it they stand upright,
# above it they lean out toward the corners (TAIL_LEAN real mm at the top), and their faces are
# concave, following the tail panel's hollow: the bend is set furthest forward and the face sweeps
# back above it (TAIL_BOW print mm at the top) and, less steeply, below it. From a rear three-quarter
# view each reads as a chevron pointing away from the viewer.
TAIL_LEAN, TAIL_BOW, TAIL_BEND = 10.0, 1.4, 0.35
TAIL_BOW_SHIFT = 0.3            # of TAIL_BOW: how far behind the nominal face the bend sits
GAS_CAP = (0.0, 814.0, 71.0)                   # pocket; the cap is FIT smaller
TRUNK_LOCK = (0.0, 903.0, 16.5)
LOCK_POCKET_R = 24.0
# spaced block capitals under the trim: (letter, width) real mm, 16 mm tall
LETTERS = [("M", 28.0), ("U", 23.0), ("S", 19.0), ("T", 20.0), ("A", 29.0), ("N", 25.0), ("G", 24.0)]
LETTER_PITCH, LETTER_H, LETTER_TOP_DROP = 145.0, 16.0, 37.0    # letter tops this far below the deck edge's trim line
LETTER_FONT = "/System/Library/Fonts/Supplemental/Rockwell.ttc"   # heavy slab serif, stretched wide


def _dense_rows(rows, df, span=(0.0, 1.0)):
    """A bumper profile [(height fraction, thickness)] with rows interpolated in so that none between the heights
    `span` are more than df apart."""
    out = [rows[0]]
    for (f0, d0), (f1, d1) in zip(rows[:-1], rows[1:]):
        k = max(1, math.ceil(round((f0 - f1) / df, 6))) if span[0] <= f1 and f0 <= span[1] else 1
        out += [(f0 + (f1 - f0) * j / k, d0 + (d1 - d0) * j / k) for j in range(1, k + 1)]
    return out


FRONT_BUMPER_Z = (470.0, 566.0)
REAR_BUMPER_Z = (629.0, 738.0)
# the rear blade: a broad top sloping up to just under the lamps, a crisp crease, then the face;
# (height fraction, forward thickness print mm), top first; between 0.15 and the top's last row rows are
# interpolated in every 0.03 at most, which leaves the blade's section as it is but gives the curled ends' rolled lip
# rows to bend on, and the face's back rows to follow the body's bulge between them (it would come nearer than GAP);
# not along the edges, where small faces would only make them read thin
REAR_BUMPER_PROFILE = _dense_rows([(1.0, 0.25), (0.94, 0.65), (0.88, 1.1), (0.75, 2.0), (0.72, 2.3), (0.69, 2.35), (0.45, 2.25),
                                   (0.15, 1.65), (0.0, 1.05)], 0.03, (0.15, 0.94))
# it wraps just round the tail corners (rays from a point ahead of the tail, out to where the flank
# turns forward) into blunt full-section ends that curl up beside the taillights; they stand straight
# back off the corners, as the quarter extensions above them do, so their faces and sides run flush
# with the extensions' and the quarter panels'
REAR_BUMPER_CENTER_X, REAR_BUMPER_WRAP = 4150.0, math.radians(68.8)
REAR_BUMPER_RISE = 45.0                       # past the outer lamps the top curls up round the corner, level again at
                                              # the ends, where the quarter extensions stand on it (body.CORNER_EXT's foot)
# the face below the crease climbs only from |y| 770 over this far (the top: from 740 over 110), so the crease runs
# on level past the lamps and turns up later and tighter, as in photo 3, while the top above it already rides up onto
# the extension's foot
REAR_BUMPER_FACE_RISE = (770.0, 80.0)
# the bottom edge rounds up into the end: a slow turn off the bottom (a fillet of radius 60), a straight run at 48 deg
# that would meet the end (|y| 852) 62.5 up, then a turn of radius 50 that stands vertical just at the end; arcs and
# line meet tangent, so the outline has no kink (a superellipse under 2 turns infinitely fast where it meets the
# vertical, which the end stations showed as a crease). Photo 3's corner is tighter low down, but the quarter
# panel's lower corner right behind the bumper follows this outline: any tighter and the red panel shows under it
REAR_BUMPER_CORNER = (852.0, 62.5, 48.0, 60.0, 50.0)
# the face climbs the curled end from |y| 806 to its top at 845 (bumpers.sweep's curl), slowly at first and then
# faster, so the lip above it turns up in a J into the quarter extension's corner trim (photo 3)
REAR_BUMPER_CURL = (806.0, 845.0, 1.5)
BUMPER_PEGS_Y = (-300.0, 300.0)
# guards: (y positions, top z, drop, width real mm, rounded capsule); black rubber at the rear
FRONT_GUARDS = ((-480.0, 480.0), 494.0, 170.0, 31.2, True)      # chrome capsules running down the apron, as on the car
FRONT_BUMPER_SIDE_T = 0.6                     # print mm: the blade's thickness where it wraps along the fenders
REAR_GUARDS = ((-227.0, 227.0), 690.0, 160.0, 38.0, True)      # rubber-faced capsules
# two round bolt heads low on the rear blade's face, outboard of the plate (y, z real mm, as in photo 3):
# low domes BOLT_R round and BOLT_H high (real mm; about 1 mm across and 0.3 mm proud printed), square to the face
REAR_BOLTS = [(s * 565.0, 660.0) for s in (-1, 1)]
BOLT_R, BOLT_H = 13.0, 7.0
FRONT_WRAP_END_X = 400.0
PLATE_NOTCH = (-172.0, 600.0, 172.0, 680.0)   # cut-out in the rear blade's lower edge over the plate

# underside behind the rear axle: the floor climbs right behind the axle boss slot, so the quarters
# and valance end ~0.5 m off the ground with the axle, tires and exhaust in view below, as on the
# car (the flat underside ahead of it is the print bed)
REAR_FLOOR_Z = 488.0
# Outboard of REAR_UNDER_Y the quarters hang lower than that floor: their lower edge (x, z) eases up
# from behind the wheel to the floor at the tail, keeping just above the line of sight under the
# valance from behind, so the tires show below it as on the car. The quarters roll under toward it
# (body.QUARTER_TUCK), so the edge comes where the drawn-in skin already faces partly down. Across
# the car the step rolls down over QUARTER_ROLL (real mm), shrinking away as it rises.
REAR_UNDER_Y, QUARTER_ROLL = 610.0, 80.0
QUARTER_EDGE = [(3935.0, 420.0), (4100.0, 432.0), (4250.0, 455.0), (4350.0, 477.0), (4400.0, REAR_FLOOR_Z), (4460.0, REAR_FLOOR_Z)]


def body_z_bottom():
    from body import Z_BOTTOM
    return Z_BOTTOM
REAR_UNDER = F.rounded_poly([(3610, 100), (3610, 250), (3650, 300), (3800, REAR_FLOOR_Z - 3), (3860, REAR_FLOOR_Z),
                             (4800, REAR_FLOOR_Z), (4800, 100)], [0, 30, 50, 60, 40, 0, 0])

def louver_slots():
    """Vertical slats in a panel on the C-pillar sail, behind the quarter glass."""
    slots = []
    for k in range(9):
        x0 = 2988 + 44 * k
        top = 1222 - (x0 - 2985) * 0.12 - 12
        slots.append(rect(x0, 1066, x0 + 18, top, 8))
    return slots


def tail_lamps(side):
    """[(bezel (y0, y1), lens (y0, y1))] real mm for one side's three lamps."""
    out = []
    for yc in TAIL_LAMP_Y:
        y = side * yc
        out.append(((y - TAIL_BEZEL_W / 2, y + TAIL_BEZEL_W / 2), (y - TAIL_LENS_W / 2, y + TAIL_LENS_W / 2)))
    return out


def _tail_u(z):
    """Height along a taillight measured from its bend, in units of the bend-to-top length
    (1 at the top, -TAIL_BEND / (1 - TAIL_BEND) at the foot)."""
    t = max(0.0, min(1.0, (z - TAIL_BAR_Z0) / (TAIL_BAR_Z1 - TAIL_BAR_Z0)))      # 0 at the foot
    return (t - TAIL_BEND) / (1.0 - TAIL_BEND)


def tail_lean(side, z):
    """Sideways offset (real mm) of a taillight at height z: upright below the bend, leaning out
    above it; centred so the lamp keeps its place on average."""
    return side * TAIL_LEAN * (max(0.0, _tail_u(z)) ** 1.3 - (1.0 - TAIL_BEND) / 2.3)


def tail_bow(z):
    """How far (print mm) a taillight's face stands out at height z beyond its nominal plane:
    concave, deepest at the bend."""
    return TAIL_BOW * (abs(_tail_u(z)) ** 1.2 - TAIL_BOW_SHIFT)


def lamp_solid(name, side, y0, y1, z0, z1, r, x_back, x_front, bow_back=False, bow_front=True, n=24):
    """A taillight element (or its pocket): the rear-view rounded rectangle y0..y1 x z0..z1 (real mm,
    corner radius r) curved like the lamps (tail_lean), standing from x_back to x_front (print mm,
    along +X). Its front, and optionally its back, follows the lamp face's bow (tail_bow); flat backs
    let the parts print lying on them."""
    zs = [z0 + (z1 - z0) * k / n for k in range(n + 1)]
    if r > 0:                                    # rows round the rounded corners
        corner = [r * (1 - math.cos(a)) for a in (0.3, 0.6, 0.9, 1.2)]
        zs += [z0 + d for d in corner] + [z1 - d for d in corner]
    zs = sorted(set(round(z, 4) for z in zs))
    bm = bmesh.new()
    rings = []
    for z in zs:
        dz = min(z - z0, z1 - z, r)
        inset = r - math.sqrt(max(0.0, r * r - (r - dz) ** 2)) if r > 0 else 0.0
        lean, bow = tail_lean(side, z), tail_bow(z)
        yl, yr = y0 + inset + lean, y1 - inset + lean
        xb, xf = x_back + (bow if bow_back else 0.0), x_front + (bow if bow_front else 0.0)
        rings.append([bm.verts.new((x, y * SCALE, z * SCALE)) for x, y in ((xb, yl), (xf, yl), (xf, yr), (xb, yr))])
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def rear_bumper_rise(y):
    """How far the rear bumper's top has curled up at |y| (real mm): from just outboard of the lamps, levelling
    off over the ends so that their tops run level into the corners."""
    return REAR_BUMPER_RISE * _smooth((abs(y) - 740.0) / 110.0)


def rear_bumper_face_rise(y):
    """How far the rear bumper's face (up to its crease) has risen at |y| (real mm): later than the top."""
    y0, span = REAR_BUMPER_FACE_RISE
    return REAR_BUMPER_RISE * _smooth((abs(y) - y0) / span)


def rear_bumper_curl(y):
    """How far up the rear bumper's curled end its face has filled at |y| (real mm), 0..1."""
    y0, y1, power = REAR_BUMPER_CURL
    return max(0.0, min(1.0, (abs(y) - y0) / (y1 - y0))) ** power


def rear_bumper_bottom(y):
    """How far the rear bumper's bottom edge has rounded up at |y| (real mm): fillet, straight run, fillet."""
    ye, zl, angle, r1, r2 = REAR_BUMPER_CORNER
    a, y = math.radians(angle), abs(y)
    ya = ye - zl / math.tan(a) - r1 * math.tan(a / 2)     # the bottom fillet leaves the level bottom
    yb = ye - r2 * (1 - math.sin(a))                      # the top fillet leaves the straight run
    if y <= ya:
        return 0.0
    if y <= ya + r1 * math.sin(a):
        return r1 - math.sqrt(r1 * r1 - (y - ya) ** 2)
    if y <= yb:
        return zl + (y - ye) * math.tan(a)
    zc = zl + r2 * math.tan(math.pi / 4 - a / 2)          # where it stands vertical, at the end
    return zc - math.sqrt(max(0.0, r2 * r2 - (min(y, ye) - ye + r2) ** 2))


def _tail_x(tree, y, z):
    return hit_w(tree, "+X", y, z) / SCALE


def tail_trim_path(tree):
    """Centre line of the chrome strip framing the tail panel, in the rear view (u = y, v = z): up
    the left corner, across, down the right corner to the bumper's end. Across the middle it is a
    crowned curve anchored on the deck lid's trailing edge at the centre line (traced on the body),
    falling to the S-step; outboard it runs level across the quarter-extension fins, then turns
    down their corners, which are traced on the body too."""
    def corner_y(z):
        # the strip runs where the quarter extension's rear face starts to turn into the side: track the
        # rearmost point reached so far, so the face rising onto a protruding extension does not stop it
        ref, y = _tail_x(tree, 500.0, z), 500.0
        while True:
            x = _tail_x(tree, y + 2.0, z)
            if x <= ref - TAIL_EDGE_DROP:
                break
            ref, y = max(ref, x), y + 2.0
        return y - TRIM_INSET

    ya, yb = TRIM_STEP_Y - TRIM_STEP_LEN / 2, TRIM_STEP_Y + TRIM_STEP_LEN / 2
    z_ref = tail_trim_ref(tree)
    za, z_low = z_ref + TRIM_STEP_TOP, z_ref + TRIM_LOW
    pts = [(y, za + (TRIM_CROWN - TRIM_STEP_TOP) * (1 - (y / ya) ** 2)) for y in [ya * k / 12 for k in range(12)]]
    for k in range(0, 11):                          # the S-step, level at both ends
        u = k / 10
        pts.append((ya + (yb - ya) * u, za + (z_low - za) * (1 - math.cos(math.pi * u)) / 2))
    yc, r = corner_y(z_low - TRIM_CORNER_R), TRIM_CORNER_R
    y = yb + 20.0
    while y < yc - r:
        pts.append((y, z_low))
        y += 20.0
    for k in range(1, 7):                           # tight corner into the leg
        a = math.pi / 2 * k / 6
        pts.append((yc - r + r * math.sin(a), z_low - r + r * math.cos(a)))
    z = z_low - r - 20.0
    while True:
        cy = corner_y(z)
        # the leg ends where the quarter extension, standing on the bumper, is full depth again
        bottom = max(REAR_BUMPER_Z[1] + rear_bumper_rise(cy) + 6.0, CORNER_EXT[2][0])
        if z - 20.0 <= bottom:
            pts.append((corner_y(bottom), bottom))
            break
        pts.append((cy, z))
        z -= 20.0
    right = F.chaikin(pts, 1)
    return [(-y, z) for y, z in reversed(right[1:])] + right


def tail_rear_x(tree, z):
    """Rearmost x (real mm) of the tail at height z across the quarter extension: the side view's outline."""
    xs = []
    for y in range(700, 861, 8):
        hit, *_ = tree.ray_cast(Vector((200.0, y * SCALE, z * SCALE)), Vector((-1.0, 0.0, 0.0)), 400.0)
        if hit is not None:
            xs.append(hit.x / SCALE)
    return max(xs)


def ext_seam(tree, n=10):
    """The quarter extension's joint in the side view [(x, z)] real mm: from where the extension stands
    full depth on the bumper's end up to EXT_SEAM_TOP, EXT_SEAM_BACK ahead of its rear face at every height."""
    z0 = CORNER_EXT[2][0]
    zs = [z0 + (EXT_SEAM_TOP - z0) * k / n for k in range(n + 1)]
    return F.chaikin([(tail_rear_x(tree, z) - EXT_SEAM_BACK, z) for z in zs], 2)


def tail_trim_ref(tree):
    """z (real mm) of the trim line under the deck lid's trailing edge at the centre line."""
    ref, z = _tail_x(tree, 0.0, 880.0), 880.0
    while _tail_x(tree, 0.0, z + 2.0) > ref - TAIL_EDGE_DROP:
        z += 2.0
    return z - TRIM_INSET


def deck_gap_path(tree, sgn):
    """The deck lid's gap on one side (sgn) as one path [(point, cast direction, width)] real mm: along
    its side edge on the top (DECKLID_SIDE, cast down), then over the tail's top roll and down the tail
    face, splitting the trim, to just above the tail panel's recess (DECKLID_REAR, cast from behind).
    Each knot casts along the surface normal where it lands (kept square to y) and the corner cutting
    carries point, direction and width along together, so the groove turns over the roll in one sweep."""
    def knot(u, v, axis, width):
        into, to3d = F.AXES[axis]
        hit, nrm, *_ = tree.ray_cast(to3d(u * SCALE, v * SCALE, 200.0), into, 400.0)
        if hit is None:
            raise ValueError(f"deck gap knot ({u:.0f}, {v:.0f}) misses the body")
        d = Vector((nrm.x, 0.0, nrm.z)).normalized()
        return (*(hit / SCALE), *(d if d.dot(into) < 0 else -d), width)

    rear = DECKLID_REAR + [(DECKLID_REAR[-1][0], RECESS_TOP + 2.0)]
    knots = [knot(x, sgn * y, "+Z", DECKLID_GAP[0]) for x, y in DECKLID_SIDE]
    knots += [knot(sgn * y, z, "+X", DECKLID_GAP[1]) for y, z in rear]
    return [(q[:3], q[3:6], q[6]) for q in F.chaikin(knots, 4)]


def quarter_floor_z(x):
    """Height (real mm) of the quarters' lower edge at station x (QUARTER_EDGE)."""
    from body import smooth_table
    return smooth_table(QUARTER_EDGE, x)


def rear_under_z(x, y, ramp):
    """Top (real mm) of the cut under the tail at (x, |y|): the floor (`ramp`, REAR_UNDER's top edge
    as an (x, z) table) and, outboard of REAR_UNDER_Y, the quarters' lower edge, rolled down to."""
    from body import lerp_table
    roll = (REAR_FLOOR_Z - quarter_floor_z(x)) * _smooth((abs(y) - REAR_UNDER_Y) / QUARTER_ROLL)
    return min(lerp_table(ramp, x), REAR_FLOOR_Z - roll)


def under_solid(name, xs, ys, top, z0):
    """Solid from z0 up to the surface z = top(x, y) over the grid xs by ys (real mm, both sorted):
    an underside cutter whose floor varies across the car as well as along it. The end caps are
    fanned from a bottom corner, so their long level edges leave no slivers."""
    bm = bmesh.new()
    t = [[bm.verts.new((x * SCALE, y * SCALE, top(x, y) * SCALE)) for y in ys] for x in xs]
    b = [[bm.verts.new((x * SCALE, y * SCALE, z0 * SCALE)) for y in (ys[0], ys[-1])] for x in xs]
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            bm.faces.new((t[i][j], t[i + 1][j], t[i + 1][j + 1], t[i][j + 1]))
        bm.faces.new((b[i][0], b[i + 1][0], t[i + 1][0], t[i][0]))
        bm.faces.new((t[i][-1], t[i + 1][-1], b[i + 1][1], b[i][1]))
        bm.faces.new((b[i][1], b[i + 1][1], b[i + 1][0], b[i][0]))
    for i in (0, -1):
        for j in range(len(ys) - 1):
            bm.faces.new((b[i][0], t[i][j], t[i][j + 1]))
        bm.faces.new((b[i][0], t[i][-1], b[i][1]))
    F.outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new(name, me)


def tail_recess_outline():
    """The panel set back below the letter band, |y| <= RECESS_HALF (just inside the tail corners and
    their trim); its bottom edge is hidden behind the bumper."""
    return rect(-RECESS_HALF, 700.0, RECESS_HALF, RECESS_TOP, 10.0)


def tail_floor(tree, y, z):
    """x (print mm) of the set-back tail panel at (y, z)."""
    return hit_w(tree, "+X", y, z) - TAIL_RECESS


def line_band(p0, p1, width):
    """Thin closed band along a segment (real mm): a panel-line groove outline."""
    d = Vector(p1) - Vector(p0)
    n = Vector((-d.y, d.x)).normalized() * (width / 2)
    a, b = Vector(p0), Vector(p1)
    return [tuple(a - n), tuple(b - n), tuple(b + n), tuple(a + n)]


FRONT_ARCH, REAR_ARCH = 394.0, 404.0            # wheel openings' radii (real mm; build.ARCH_R, REAR_ARCH_R)
REAR_LIP = dict(width=12.0, inner=3.0)         # the rear lip: a thinner chrome line hugging the opening (12 mm = 0.5 mm printed)


def rocker_trim_outline():
    from body import FRONT_AXLE_X, REAR_AXLE_X
    return rect(FRONT_AXLE_X + FRONT_ARCH + 8, 324, REAR_AXLE_X - REAR_ARCH - 8, 400, 12)


def arch_lip_segments(axle_x, radius, width=16.0, pieces=10, inner=6.0):
    """Raised molding around a wheel arch, in star-shaped pieces (side view, real mm)."""
    from body import WHEEL_RADIUS
    zc = WHEEL_RADIUS
    segs = []
    a0, a1 = math.radians(8), math.radians(172)
    for i in range(pieces):
        t0 = a0 + (a1 - a0) * i / pieces
        t1 = a0 + (a1 - a0) * (i + 1) / pieces + (math.radians(0.6) if i < pieces - 1 else 0.0)
        pts = []
        for k in range(5):
            t = t0 + (t1 - t0) * k / 4
            pts.append((axle_x - (radius - inner) * math.cos(t), zc + (radius - inner) * math.sin(t)))
        for k in range(5):
            t = t1 - (t1 - t0) * k / 4
            pts.append((axle_x - (radius + width) * math.cos(t), zc + (radius + width) * math.sin(t)))
        segs.append(pts)
    return segs


def arch_lip_path(axle_x, radius, step=8.0):
    """Centre line (side view, real mm) of a wheel arch's lip, over the same span as arch_lip_segments."""
    from body import WHEEL_RADIUS
    a0, a1 = math.radians(8), math.radians(172)
    n = max(2, int(math.ceil(radius * (a1 - a0) / step)))
    return [(axle_x - radius * math.cos(a0 + (a1 - a0) * k / n), WHEEL_RADIUS + radius * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def capsule_chain(points, r, steps=10):
    """Closed outlines of a thick polyline with round caps (each segment its own capsule)."""
    outlines = []
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
        a = math.atan2(y1 - y0, x1 - x0)
        pts = []
        for k in range(steps + 1):            # cap round the end point
            t = a - math.pi / 2 + math.pi * k / steps
            pts.append((x1 + r * math.cos(t), y1 + r * math.sin(t)))
        for k in range(steps + 1):            # cap round the start point
            t = a + math.pi / 2 + math.pi * k / steps
            pts.append((x0 + r * math.cos(t), y0 + r * math.sin(t)))
        outlines.append(pts)
    return outlines


def rect(u0, v0, u1, v1, r):
    return F.rounded_poly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], r)


def offset_rect(u0, v0, u1, v1, r, inset_print):
    i = inset_print / SCALE
    return rect(u0 + i, v0 + i, u1 - i, v1 - i, max(0.0, r - i))


# ---------------------------------------------------------------- helpers

def hit_w(tree, axis, u, v):
    """Coordinate along the outward axis where the body surface is at (u, v) (real mm)."""
    into, to3d = F.AXES[axis]
    origin = to3d(u * SCALE, v * SCALE, 200.0)
    hit, *_ = tree.ray_cast(origin, into, 400.0)
    if hit is None:
        raise ValueError(f"no surface at {axis} ({u}, {v})")
    return -hit.dot(into)


GRILLE_DEPTH, HEADLIGHT_DEPTH, TAILLIGHT_DEPTH, GAS_CAP_DEPTH = 3.0, 2.0, 2.0, 2.4
GAS_CAP_PROUD = 1.2             # the chrome cap stands ~30 mm proud of the set-back panel
TAILLIGHT_PROUD = TAIL_RECESS   # bezel faces stand off the set-back panel flush with the band above it


def grille_floor(tree):
    return hit_w(tree, "-X", 0, 715) - GRILLE_DEPTH


def headlight_floor(tree, y):
    return hit_w(tree, "-X", y, HEADLIGHT_Z) - HEADLIGHT_DEPTH


def taillight_floor(tree, y):
    """Pocket floor of the lamp centred at y: the bezels stand TAILLIGHT_PROUD off the set-back panel."""
    return tail_floor(tree, y, (TAIL_BAR_Z0 + TAIL_BAR_Z1) / 2) - TAILLIGHT_DEPTH


def gas_cap_floor(tree):
    return tail_floor(tree, GAS_CAP[0], GAS_CAP[1]) - GAS_CAP_DEPTH


def body_cutters(tree, body_mesh):
    """Return [(name, object)] cutters to subtract from the body."""
    cuts = []
    for side, axis in (("R", "+Y"), ("L", "-Y")):
        cuts.append((f"Cut_WindowOpen_{side}", F.surface_cutter(f"Cut_WindowOpen_{side}", body_mesh, axis, WINDOW_OPEN,
                                                                WINDOW_CUT_DEPTH, rings=8, tree=tree)))
        # the beltline inboard of the doors and quarter trim belongs to them (door tops, trim
        # panels): clear it from the cabin up into the window opening, so with a door open the side
        # is one opening from sill to roof rail. Ahead of the window opening the A-pillar's foot
        # stands there: under it only clear down to the door's top.
        hi = pillar_meets(lambda x: sill_z(x) + BELTLINE_TOP, BELTLINE_PILLAR)
        lo = pillar_meets(lambda x: sill_z(x) - 3.0, BELTLINE_PILLAR)
        belt = [(BELTLINE_X0, 790.0), (QUARTER_X1 - 8.0, 790.0)]
        belt += [(x, sill_z(x) + BELTLINE_TOP) for x in (QUARTER_X1 - 8.0 + (hi.x - QUARTER_X1 + 8.0) * k / 12 for k in range(13))]
        belt += [tuple(lo), (BELTLINE_X0, sill_z(BELTLINE_X0) - 3.0)]
        cuts.append((f"Cut_Beltline_{side}", F.prism_cutter(f"Cut_Beltline_{side}", axis, belt,
                                                            BELTLINE_Y[0] * SCALE, BELTLINE_Y[1] * SCALE)))
        for i, slot in enumerate(louver_slots()):
            cuts.append((f"Cut_Louver{i}_{side}", F.surface_cutter(f"Cut_Louver{i}_{side}", body_mesh, axis, slot, 0.5,
                                                                   rings=3, tree=tree)))
        cuts.append((f"Cut_ScoopCove_{side}", F.surface_cutter(f"Cut_ScoopCove_{side}", body_mesh, axis, SCOOP_COVE, 0.9,
                                                               depth_fn=cove_fade, tree=tree)))
        for i, intake in enumerate(SCOOP_INTAKES):
            cuts.append((f"Cut_ScoopIntake{i}_{side}", F.surface_cutter(f"Cut_ScoopIntake{i}_{side}", body_mesh, axis, intake, 1.6,
                                                                        rings=4, tree=tree)))
    for tag, (outline, depth) in GLASS_RECESSES.items():         # deep enough for the glass inlay too
        cuts.append((f"Cut_Glass_{tag}", F.surface_cutter(f"Cut_Glass_{tag}", body_mesh, "+Z", outline, depth + GLASS_T, tree=tree)))
    for i, sgn in enumerate((-1, 1)):            # down each side and on down the tail face, splitting the trim
        cuts.append((f"Cut_DeckLine{i}", F.surface_ribbon(f"Cut_DeckLine{i}", tree, deck_gap_path(tree, sgn), -0.35, 1.0)))
    for side, axis in (("R", "+Y"), ("L", "-Y")):        # joint between the quarter panel and its extension
        cuts.append((f"Cut_ExtSeam_{side}", F.surface_strip(f"Cut_ExtSeam_{side}", tree, axis, ext_seam(tree), 8.0, -EXT_SEAM_DEPTH, 1.0)))
    cuts.append(("Cut_DeckLine2", F.surface_cutter("Cut_DeckLine2", body_mesh, "+Z",
                                                   line_band((DECKLID_X0, -DECKLID_Y - 6), (DECKLID_X0, DECKLID_Y + 6), 13.0),
                                                   0.35, rings=2, tree=tree)))

    # grille: flat-floored pocket, the shark-nose recess
    floor = grille_floor(tree)
    cuts.append(("Cut_Grille", F.prism_cutter("Cut_Grille", "-X", GRILLE, floor, floor + 30.0)))
    for s in (-1, 1):
        y = s * HEADLIGHT_Y
        f = headlight_floor(tree, y)
        name = f"Cut_Headlight_{'L' if s < 0 else 'R'}"
        # flared bucket: the fender forms an eyebrow around a recessed lamp
        wide = F.circle(y, HEADLIGHT_Z, HEADLIGHT_R + HEADLIGHT_FLARE, 40)
        cuts.append((name, F.loft_solid(name, "-X", [(F.circle(y, HEADLIGHT_Z, HEADLIGHT_R, 40), f),
                                                     (wide, f + HEADLIGHT_DEPTH + 0.2), (wide, f + 30.0)])))
    for i, (y, z, r) in enumerate(PARK_LIGHTS):
        pocket = F.prism_cutter(f"Cut_ParkLight{i}", "+Z", F.circle(0.0, 0.0, r, 40), -PARK_DEPTH, 30.0)
        pocket.data.transform(park_light_frame(tree, y, z))
        cuts.append((f"Cut_ParkLight{i}", pocket))

    # tail: panel set back inside the trim, deeper lamp pockets, gas cap; valance plate recess
    cuts.append(("Cut_TailPanel", F.surface_cutter("Cut_TailPanel", body_mesh, "+X", tail_recess_outline(), TAIL_RECESS, tree=tree)))
    for s in (-1, 1):
        for i, ((y0, y1), _lens) in enumerate(tail_lamps(s)):
            f = taillight_floor(tree, (y0 + y1) / 2)
            name = f"Cut_Taillight_{'L' if s < 0 else 'R'}{i}"
            cuts.append((name, lamp_solid(name, s, min(y0, y1), max(y0, y1), TAIL_BAR_Z0, TAIL_BAR_Z1, 7, f, f + 30.0, bow_front=False)))
    for i, (y, z, r) in enumerate(BACKUP_LIGHTS):      # round sockets for the backup-lamp spigots: FIT clear all
        name = f"Cut_BackupSocket{i}"                  # round and behind, out past the face into the air
        cuts.append((name, F.prism_cutter(name, "+X", F.circle(y, z, backup_radius(r, BACKUP_BACK_X) + FIT / SCALE, 48),
                                          (BACKUP_BACK_X - FIT / SCALE) * SCALE, (BACKUP_FACE_X + 20.0) * SCALE)))
    py0, pz0, py1, pz1 = PLATE
    cuts.append(("Cut_PlateRecess", F.surface_cutter("Cut_PlateRecess", body_mesh, "+X", rect(py0, pz0, py1, pz1, 10), PLATE_DEPTH,
                                                     rings=3, tree=tree)))
    # one cut for the whole underside behind the axle (floor and quarters' lower edges), so the roll
    # between them is a single smooth surface
    ramp = []                                   # REAR_UNDER's top edge, front to back (its fillets can share an end)
    for x, z in REAR_UNDER[1:-1]:
        if not ramp or x > ramp[-1][0] + 0.01:
            ramp.append((x, z))
    x0, x1 = ramp[-2][0], QUARTER_EDGE[-1][0]   # level from x0; the quarters' edges reach the floor at x1
    n = round((x1 - x0) / 10.0)
    xs = [x for x, _ in ramp[:-1]] + [x0 + (x1 - x0) * k / n for k in range(1, n + 1)] + [ramp[-1][0]]
    ys = [0.0] + [REAR_UNDER_Y + QUARTER_ROLL * k / 16 for k in range(17)] + [1200.0]
    ys = sorted({s * y for y in ys for s in (-1, 1)})
    cuts.append(("Cut_RearUnder", under_solid("Cut_RearUnder", xs, ys, lambda x, y: rear_under_z(x, y, ramp), REAR_UNDER[0][1])))
    # tunnel over the differential housing (which rides on the chassis)
    cuts.append(("Cut_DiffTunnel", F.prism_cutter("Cut_DiffTunnel", "+Z", rect(3405.0, -130.0, 3665.0, 130.0, 60.0),
                                                  (body_z_bottom() - 2.0) * SCALE, 470.0 * SCALE)))
    f = gas_cap_floor(tree)
    cuts.append(("Cut_GasCap", F.prism_cutter("Cut_GasCap", "+X", F.circle(GAS_CAP[0], GAS_CAP[1], GAS_CAP[2], 32), f, f + 30.0)))
    # shallow pocket round the trunk lock, running down into the gas cap's opening
    ly, lz, _ = TRUNK_LOCK
    w = tail_floor(tree, ly, lz)                  # a dished pocket: its wall slopes in to the floor
    cuts.append(("Cut_LockPocket", F.loft_solid("Cut_LockPocket", "+X", [(F.circle(ly, lz, LOCK_POCKET_R - 7.0, 32), w - 0.2),
                                                                         (F.circle(ly, lz, LOCK_POCKET_R, 32), w),
                                                                         (F.circle(ly, lz, LOCK_POCKET_R, 32), w + 1.0)])))

    # bumper peg holes
    for axis, (z0, z1), tag in (("-X", FRONT_BUMPER_Z, "F"), ("+X", REAR_BUMPER_Z, "R")):
        zc = (z0 + z1) / 2
        for y in BUMPER_PEGS_Y:
            f = hit_w(tree, axis, y, zc) - PEG_LEN - 0.4
            name = f"Cut_PegHole_{tag}{'L' if y < 0 else 'R'}"
            cuts.append((name, F.prism_cutter(name, axis, F.circle(y, zc, PEG_HOLE_R / SCALE, 20), f, f + 30.0)))
    return cuts


# ---------------------------------------------------------------- parts

def _bumper(name, tree, axis, z_range, center_x, theta0, theta1, guards, rise=None, bottom=None, face_rise=None, **shape):
    import bumpers
    z0, z1 = (z * SCALE for z in z_range)
    real = (lambda fn: (lambda p: fn(p.y / SCALE) * SCALE))
    part, path, normals = bumpers.sweep(name, tree, Vector((center_x * SCALE, 0, 0)), z0, z1, theta0, theta1,
                                        real(rise) if rise else None, bottom=real(bottom) if bottom else None,
                                        face_rise=real(face_rise) if face_rise else None, **shape)
    ys, top, drop, width, rounded = guards
    pieces = [bumpers.guard(f"{name}_Guard{'L' if y < 0 else 'R'}", path, normals, y, top * SCALE, drop * SCALE, width * SCALE / 2,
                            rounded=rounded, tree=tree, clear=shape.get("clear")) for y in ys]
    zc = (z_range[0] + z_range[1]) / 2
    for y in BUMPER_PEGS_Y:
        w = hit_w(tree, axis, y, zc)
        # diamond section: 45 degree flanks print without support; axis matches the body's peg holes
        r = PEG_R / SCALE
        diamond = [(y + r, zc), (y, zc + r), (y - r, zc), (y, zc - r)]
        pieces.append(F.prism_cutter(f"{name}_Peg{'L' if y < 0 else 'R'}", axis, diamond, w - PEG_LEN, w + 0.6))
    return part, pieces


def grille_parts(tree):
    """Grille insert: base plate, egg-crate grid, corral emblem with bars, fog lamps (unioned in build)."""
    floor = grille_floor(tree)
    u0, v0, u1, v1 = -GRILLE_Y, GRILLE_Z0, GRILLE_Y, GRILLE_Z1
    plate = F.prism_cutter("Grille", "-X", offset_rect(u0, v0, u1, v1, GRILLE_R, FIT), floor, floor + 0.9)
    pieces = []
    rib, pitch = 16.0, 42.0          # ~0.67 mm ribs on a ~1.75 mm grid
    top = floor + 1.5
    border = SURROUND_W / SCALE + FIT / SCALE + 6     # ribs stop short of the chrome surround
    v = v0 + border
    k = 0
    while v + rib < v1 - border:
        pieces.append(F.prism_cutter(f"Grille_RibH{k}", "-X", rect(u0 + border, v, u1 - border, v + rib, 0), floor + 0.8, top))
        v += pitch
        k += 1
    u = u0 + border
    k = 0
    while u + rib < u1 - border:
        pieces.append(F.prism_cutter(f"Grille_RibV{k}", "-X", rect(u, v0 + border, u + rib, v1 - border, 0), floor + 0.8, top))
        u += pitch
        k += 1
    vc = (v0 + v1) / 2 + 10
    # horizontal bars from the corral to the fog lamps
    pieces.append(F.prism_cutter("Grille_BarL", "-X", rect(-FOG_Y + FOG_R - 10, vc - 8, -CORRAL_W + 5, vc + 8, 0), floor + 0.8, top + 0.4))
    pieces.append(F.prism_cutter("Grille_BarR", "-X", rect(CORRAL_W - 5, vc - 8, FOG_Y - FOG_R + 10, vc + 8, 0), floor + 0.8, top + 0.4))
    # pockets for the separate chrome corral emblem and fog lamps
    holes = [F.prism_cutter("Grille_CorralPocket", "-X", rect(-CORRAL_W, vc - CORRAL_H, CORRAL_W, vc + CORRAL_H, 22),
                            floor + 0.4, floor + 4.0)]
    for s in (-1, 1):
        holes.append(F.prism_cutter(f"Grille_FogPocket{'L' if s < 0 else 'R'}", "-X", F.circle(s * FOG_Y, vc, FOG_R, 32),
                                    floor + 0.4, floor + 4.0))
    return plate, pieces, holes


# The running horse, traced from a close-up photo of the real emblem (pony_trace.py ->
# pony_outline.json: pixel units, y up, galloping toward the viewer's left). The corral
# window is sized around it so the nose, tail tip, hoof and mane reach into the frame and
# hold the cut-out horse, with the black grille showing through around it like on the car.
PONY_LENGTH = 215.0         # nose to tail tip (real mm)
CORRAL_FRAME = 16.0         # frame width (real mm, ~0.67 mm)
# space between the horse and the inside of the frame (real mm, viewer's left/right);
# negative = the hoof and tail tip reach into the frame, which holds the cut-out horse
MARGIN_NOSE, MARGIN_TAIL, MARGIN_TOP, MARGIN_HOOF = 16.0, -4.0, 9.0, -4.0


def _pony_points():
    """Traced outline in real mm (viewer's right = +x, up = +y), positioned so the corral
    window around it is centred on the origin."""
    import json
    import os
    with open(os.path.join(os.path.dirname(__file__), "pony_outline.json")) as f:
        pts = json.load(f)["points"]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    s = PONY_LENGTH / (max(xs) - min(xs))
    pts = [((x - min(xs)) * s, (y - min(ys)) * s) for x, y in pts]
    w, h = max(p[0] for p in pts), max(p[1] for p in pts)
    wx0, wx1 = -MARGIN_NOSE, w + MARGIN_TAIL          # window extents in horse coordinates
    wy0, wy1 = -MARGIN_HOOF, h + MARGIN_TOP
    cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
    return [(x - cx, y - cy) for x, y in pts], (wx1 - wx0) / 2, (wy1 - wy0) / 2


_PONY, WINDOW_HALF_W, WINDOW_HALF_H = _pony_points()
CORRAL_W, CORRAL_H = WINDOW_HALF_W + CORRAL_FRAME, WINDOW_HALF_H + CORRAL_FRAME   # half sizes (real mm)


def pony_outlines(cu, cv):
    """Horse outline around (cu, cv) in grille-view real mm, where the viewer's left is +u."""
    return [[(cu - x, cv + y) for x, y in _PONY]]


def grille_chrome_parts(tree):
    """Separate chrome pieces that sit in the grille insert: the corral emblem and two fog lamps.

    The corral is an open frame with the cut-out running horse inside, so the black grille floor
    shows through around the horse just like on the car."""
    floor = grille_floor(tree)
    vc = (GRILLE_Z0 + GRILLE_Z1) / 2 + 10
    i = FIT / SCALE
    corral = F.prism_cutter("Corral", "-X", rect(-CORRAL_W + i, vc - CORRAL_H + i, CORRAL_W - i, vc + CORRAL_H - i, 22 - i),
                            floor + 0.4, floor + 1.8)
    window = F.prism_cutter("Corral_Window", "-X", rect(-WINDOW_HALF_W, vc - WINDOW_HALF_H, WINDOW_HALF_W, vc + WINDOW_HALF_H, 8),
                            floor, floor + 3.0)
    pony = [F.prism_cutter(f"Corral_Pony{k}", "-X", outline, floor + 0.4, floor + 1.9)
            for k, outline in enumerate(pony_outlines(0.0, vc))]
    fogs = [sealed_beam(f"FogLamp_{tag}", f"FogRing_{tag}", f"FogLens_{tag}", s * FOG_Y, vc, FOG_R - i, floor + 0.4, floor + 2.1)
            for s, tag in ((-1, "L"), (1, "R"))]
    return corral, window, pony, fogs


def sealed_beam(name, ring_name, lens_name, cy, cz, r, w0, w1, axis="-X"):
    """(part, union pieces, cut pieces): a round lamp insert facing along `axis`, radius r (real mm),
    from w0 to w1 (print mm), its face a chrome retaining ring round a domed lens. The ring is what
    is left of the rim once the well inside it is cut; the dome's foot reaches just under the ring
    so the union closes cleanly."""
    ri = r - LAMP_RING_W
    seat = w1 - LAMP_RING_H
    part = F.prism_cutter(name, axis, F.circle(cy, cz, r, 48), w0, w1)
    well = F.prism_cutter(ring_name, axis, F.circle(cy, cz, ri, 48), seat, w1 + 1.0)
    rf = ri + 0.8
    sections = [(F.circle(cy, cz, rf, 48), seat - 0.1)]
    for k in range(9):
        a = math.pi / 2 * 0.95 * k / 8
        sections.append((F.circle(cy, cz, rf * math.cos(a), 48), seat + LAMP_DOME * math.sin(a)))
    return part, [F.loft_solid(lens_name, axis, sections)], [well]


def park_light_frame(tree, y, z):
    """World matrix of a parking lamp's own frame: origin on the valance at (y, z) (real mm), +Z
    along the surface's outward normal there."""
    hit, normal, *_ = tree.ray_cast(Vector((-200.0, y * SCALE, z * SCALE)), Vector((1.0, 0.0, 0.0)), 400.0)
    if hit is None:
        raise ValueError(f"parking lamp at ({y:.0f}, {z:.0f}) misses the body")
    n = normal.normalized() if normal.x < 0 else -normal.normalized()
    return Matrix.Translation(hit) @ n.to_track_quat('Z', 'Y').to_matrix().to_4x4()


SURROUND_W = 1.0       # chrome grille surround ring width (print mm)


def grille_surround(tree):
    """Chrome ring framing the grille; sits on the insert's flat border inside the pocket. The nose
    rakes back toward the bottom, so the flat ring would stand proud of the skin along its lower
    edge, where the front bumper's top hugs the skin: it is trimmed to stay just under the skin.
    Returns (ring, cutters)."""
    floor = grille_floor(tree)
    u0, v0, u1, v1 = -GRILLE_Y, GRILLE_Z0, GRILLE_Y, GRILLE_Z1
    outer = offset_rect(u0, v0, u1, v1, GRILLE_R, FIT)
    inner = offset_rect(u0, v0, u1, v1, GRILLE_R, FIT + SURROUND_W)
    ring = F.prism_cutter("GrilleSurround", "-X", outer, floor + 0.9, floor + 2.0)
    hole = F.prism_cutter("GrilleSurround_Hole", "-X", inner, floor + 0.5, floor + 2.5)
    proud = F.surface_solid("GrilleSurround_Skin", None, "-X", rect(u0 - 40.0, v0 - 40.0, u1 + 40.0, v1 + 40.0, GRILLE_R),
                            lambda u, v: -0.1, lambda u, v: 3.0, tree=tree)
    return ring, [hole, proud]


def glass_parts(tree, body_mesh):
    """The windshield and backlight inlays: each fills its recess from the glass face down to the
    floor the body cutter left, on the same projected grid, so it meets the body face to face."""
    return [F.surface_solid(f"Glass_{tag}", body_mesh, "+Z", outline, lambda u, v, d=depth: -(d + GLASS_T),
                            lambda u, v, d=depth: -d, tree=tree)
            for tag, (outline, depth) in GLASS_RECESSES.items()]


def body_unions(tree, body_mesh):
    """Raised chrome on the body: tail trim, windshield and rear-glass surrounds, rocker trim and arch
    lips (the door handles and locks are on the doors)."""
    from body import FRONT_AXLE_X, REAR_AXLE_X

    adds = [("Add_TailTrim", F.surface_strip("Add_TailTrim", tree, "+X", tail_trim_path(tree), TRIM_W, -0.4, 0.3, square=True)),
            # chrome surround: a raised band straddling the glass edge; the glass recess then trims its inside
            ("Add_RearGlassTrim", F.surface_strip("Add_RearGlassTrim", tree, "+Z", F.resample(F.offset_closed(REAR_GLASS, 5.5), 20.0),
                                                  17.0, -0.4, 0.25, closed=True)),
            ("Add_WindshieldTrim", F.surface_strip("Add_WindshieldTrim", tree, "+Z", F.resample(F.offset_closed(WINDSHIELD, 5.5), 20.0),
                                                   17.0, -0.4, 0.25, closed=True))]

    for side, axis in (("R", "+Y"), ("L", "-Y")):        # (door handles and locks live on the doors)
        adds.append((f"Add_RockerTrim_{side}", F.surface_solid(
            f"Add_RockerTrim_{side}", body_mesh, axis, rocker_trim_outline(), lambda u, v: -0.4, lambda u, v: 0.35, rings=6, tree=tree)))
        for tag, ax in (("F", FRONT_AXLE_X), ("R", REAR_AXLE_X)):
            if tag == "R":      # one swept band: no piece joints or centre fans to kink on the rolled-under skin
                name = f"Add_ArchLipR_{side}"
                r0, r1 = REAR_ARCH - REAR_LIP["inner"], REAR_ARCH + REAR_LIP["width"]
                adds.append((name, F.surface_strip(name, tree, axis, arch_lip_path(ax, (r0 + r1) / 2), r1 - r0, -0.4, 0.3)))
                continue
            segs = arch_lip_segments(ax, FRONT_ARCH)
            for i, seg in enumerate(segs):
                name = f"Add_ArchLip{tag}{i}_{side}"
                adds.append((name, F.surface_solid(name, body_mesh, axis, seg, lambda u, v: -0.4, lambda u, v: 0.3,
                                                   rings=3, tree=tree, step=0.3)))
    return adds


def drip_rail(name, tree, axis):
    """Chrome drip moulding just outside the side window opening: along the roof rail and down the
    A-pillar's rear edge to the belt (the part of the outline from the pillar's foot to the rail's
    rear corner), standing proud of the skin."""
    d0, d1, proud = DRIP_RAIL
    path = F.offset_closed(WINDOW_OPEN, (d0 + d1) / 2)[OPENING_STEPS + 1:WINDOW_OPEN_UPPER]     # from above the foot's fillet
    return F.surface_strip(name, tree, axis, path, d1 - d0, -0.3, proud)


# front fender emblem, just behind the wheel arch: a vertical red/white/blue tri-bar with the
# running horse across it, and small spaced MUSTANG letters running back toward the door gap.
# (side-view x, z real mm; the two sides are mirror images: the horse gallops forward, red leads)
FENDER_BADGE = (1240.0, 592.0)                  # tri-bar centre
FENDER_TRIBAR = (24.0, 116.0)                   # width, height
FENDER_PONY = 96.0                              # nose to tail
FENDER_LETTERS = (1290.0, 40.0, 562.0, 18.0)    # first letter's centre x, pitch, centre z, cap height (widely spaced)


SCOOP_RIBS, SCOOP_RIB_H = 3, 12.0               # horizontal body-colour louvers across each scoop opening (real mm tall)


def scoop_ribs(tree):
    """[(name, solid)] louvers across the side-scoop openings, standing from the intake floor to just
    under the skin, their faces rounded top to bottom."""
    adds = []
    for side, axis in (("R", "+Y"), ("L", "-Y")):
        for i, intake in enumerate(SCOOP_INTAKES):
            xs, zs = [p[0] for p in intake], [p[1] for p in intake]
            for k in range(SCOOP_RIBS):
                zc = min(zs) + (max(zs) - min(zs)) * (k + 1) / (SCOOP_RIBS + 1)
                name = f"BodyScoopRib{i}{k}_{side}"
                # run into the opening's end walls, so each rib bridges between them instead of jutting out
                adds.append((name, F.surface_solid(name, None, axis, rect(min(xs) - 4.0, zc - SCOOP_RIB_H / 2, max(xs) + 4.0,
                                                                          zc + SCOOP_RIB_H / 2, 0), lambda u, v: -1.7,
                                                   lambda u, v, zc=zc: -0.3 - 0.35 * ((v - zc) / (SCOOP_RIB_H / 2)) ** 2,
                                                   rings=4, tree=tree, step=0.2)))
    return adds


def fender_badges(tree):
    """[(name, solid)] the fender emblems, standing a hair proud of the skin."""
    adds = []
    bx, bz = FENDER_BADGE
    tw, th = FENDER_TRIBAR
    for side, axis, viewer_left, x_dir in (("R", "+Y", 1, (-1, 0, 0)), ("L", "-Y", -1, (1, 0, 0))):
        w = hit_w(tree, axis, bx, bz)
        bar = rect(bx - tw / 2, bz - th / 2, bx + tw / 2, bz + th / 2, 3.0)
        adds.append((f"Add_FenderBar_{side}", F.prism_cutter(f"Add_FenderBar_{side}", axis, bar, w - 0.3, w + 0.15)))
        stripe = tw / 3 - 2.0
        for k, colour in enumerate("RWB"):       # red forward
            sx = bx + (k - 1) * tw / 3
            band = rect(sx - stripe / 2, bz - th / 2 + 6.0, sx + stripe / 2, bz + th / 2 - 6.0, 0)
            adds.append((f"FenderTri{colour}_{side}", F.prism_cutter(f"FenderTri{colour}_{side}", axis, band, w - 0.3, w + 0.2)))
        pony = pony_at(bx, bz - 8.0, FENDER_PONY, -1)          # u = x on both sides: -u is forward
        adds.append((f"Add_FenderPony_{side}", F.prism_cutter(f"Add_FenderPony_{side}", axis, pony, w - 0.3, w + 0.3)))
        lx, pitch, lz, lh = FENDER_LETTERS
        # the letters run back from the emblem and read left to right: M first on the left side,
        # where the viewer's left is forward; G first (nearest the emblem) on the right side
        word = "MUSTANG" if viewer_left < 0 else "MUSTANG"[::-1]
        for k, ch in enumerate(word):
            x = lx + k * pitch
            surface = hit_w(tree, axis, x, lz) / SCALE
            y = surface if axis == "+Y" else -surface
            adds.append((f"Add_FenderLetter{k}_{side}", F.text_solid(f"Add_FenderLetter{k}_{side}", ch, lh, 0.2, (x, y, lz), x_dir,
                                                                     (0, 0, 1), font=LETTER_FONT, bold=0.02, center=True)))
    return adds


def body_late_unions(tree, body_mesh):
    """[(name, solid)] chrome added after the body cutters (the recesses would remove them): the drip
    mouldings over the side windows, spaced MUSTANG letters on the band under the trim, the fender
    emblems, and the trunk lock rising from its pocket."""
    z_top = tail_trim_ref(tree) - LETTER_TOP_DROP
    z = z_top - LETTER_H / 2
    adds = []
    for k, (ch, w) in enumerate(LETTERS):
        y = (k - (len(LETTERS) - 1) / 2) * LETTER_PITCH
        surface = _tail_x(tree, y, z)
        adds.append((f"Add_Letter{k}", F.text_solid(f"Add_Letter{k}", ch, LETTER_H, 0.25, (surface, y, z), (0, 1, 0), (0, 0, 1),
                                                    font=LETTER_FONT, width=w, bold=0.02, center=True)))
    for side, axis in (("R", "+Y"), ("L", "-Y")):
        adds.append((f"Add_DripRail_{side}", drip_rail(f"Add_DripRail_{side}", tree, axis)))
    adds += fender_badges(tree) + scoop_ribs(tree)
    ly, lz, lr = TRUNK_LOCK
    adds.append(("Add_TrunkLock", F.surface_solid("Add_TrunkLock", body_mesh, "+X", F.circle(ly, lz, lr, 24),
                                                  lambda u, v: -0.4 - TAIL_RECESS - 0.2, lambda u, v: -TAIL_RECESS,
                                                  rings=2, tree=tree, step=0.3)))
    return adds


def body_late_cuts(tree, body_mesh):
    """[(name, cutter)] details cut into the late unions: the lock's sunk face and keyway."""
    ly, lz, lr = TRUNK_LOCK
    return [("Cut_LockFace", F.surface_cutter("Cut_LockFace", body_mesh, "+X", F.circle(ly, lz, lr - 4.0, 24), TAIL_RECESS + 0.05,
                                              out=-TAIL_RECESS + 0.3, rings=2, tree=tree)),
            ("Cut_Keyway", F.surface_cutter("Cut_Keyway", body_mesh, "+X", rect(ly - 1.2, lz - 4.0, ly + 1.2, lz + 4.0, 0.5),
                                            TAIL_RECESS + 0.15, out=-TAIL_RECESS + 0.3, rings=2, tree=tree))]


def pony_at(cu, cv, length, viewer_left):
    """Running-horse outline `length` real mm long around (cu, cv), galloping toward the viewer's
    left, which is the +u or -u direction (viewer_left = +1 / -1) in the projection used."""
    k = length / PONY_LENGTH
    return [(cu - viewer_left * x * k, cv + y * k) for x, y in _PONY]


def lamp_parts(tree):
    parts = []
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        y = s * HEADLIGHT_Y
        f = headlight_floor(tree, y)
        # on the bucket floor, its lens ~0.6 mm behind the fender eyebrow
        parts.append(sealed_beam(f"Headlight_{tag}", f"HeadRing_{tag}", f"HeadLens_{tag}", y, HEADLIGHT_Z, HEADLIGHT_R - FIT / SCALE,
                                 f, f + 1.35))
        # each lamp: a red lens plate with its raised lens, under a chrome bezel whose face stands
        # TAILLIGHT_PROUD off the set-back panel and whose window frames the deep-set lens. All of
        # it curves like the real lamps (lamp_solid); the plate and bezel keep flat backs.
        i = FIT / SCALE
        for k, ((by0, by1), (ly0, ly1)) in enumerate(tail_lamps(s)):
            by0, by1, ly0, ly1 = min(by0, by1), max(by0, by1), min(ly0, ly1), max(ly0, ly1)
            f = taillight_floor(tree, (by0 + by1) / 2)
            top = f + TAILLIGHT_DEPTH + TAILLIGHT_PROUD
            z0, z1, lz0, lz1 = TAIL_BAR_Z0, TAIL_BAR_Z1, TAIL_LENS_Z0, TAIL_LENS_Z1
            plate = lamp_solid(f"Taillight_{tag}{k}", s, by0 + i, by1 - i, z0 + i, z1 - i, 7 - i, f, f + 1.0, bow_front=False)
            lens = lamp_solid(f"Taillight_{tag}{k}_Lens", s, ly0 + i, ly1 - i, lz0 + i, lz1 - i, 6 - i, f + 0.8, top - 0.55)
            bezel = lamp_solid(f"TailBezel_{tag}{k}", s, by0 + i, by1 - i, z0 + i, z1 - i, 7 - i, f + 1.0, top)
            window = lamp_solid(f"TailBezel_{tag}{k}_Win", s, ly0, ly1, lz0, lz1, 6, f + 0.7, top + 1.0 + TAIL_BOW, bow_front=False)
            parts.append((plate, [lens], []))
            parts.append((bezel, [], [window]))
    for y, z, r in PARK_LIGHTS:                  # modelled in their own frame (lens up), placed on the valance
        tag = "L" if y < 0 else "R"
        part, pieces, holes = sealed_beam(f"ParkLight_{tag}", f"ParkRing_{tag}", f"ParkLens_{tag}", 0.0, 0.0, r - FIT / SCALE,
                                          -PARK_DEPTH, -0.1, axis="+Z")
        part.matrix_world = park_light_frame(tree, y, z)
        for piece in pieces + holes:
            piece.parent = part
        parts.append((part, pieces, holes))
    # gas cap: chrome rim, thin dark ring, light spun face with the red-white-blue tri-bar and the
    # running horse in front of it
    f = gas_cap_floor(tree)
    gy, gz, gr = GAS_CAP
    top = f + GAS_CAP_DEPTH + GAS_CAP_PROUD
    ring = F.prism_cutter("GasCap_Ring", "+X", F.circle(gy, gz, 58.0, 48), top - 0.15, top + 1.0)
    face = F.prism_cutter("GasCap_Face", "+X", F.circle(gy, gz, 52.5, 48), top - 0.4, top - 0.08)
    bars = [F.prism_cutter("GasCap_TriFrame", "+X", rect(gy - 9.0, gz - 36.0, gy + 9.0, gz + 20.0, 1.5), top - 0.2, top - 0.05)]
    bars += [F.prism_cutter(f"GasCap_Tri{c}", "+X", rect(gy + dy - 2.5, gz - 33.0, gy + dy + 2.5, gz + 17.0, 0), top - 0.2, top - 0.02)
             for c, dy in (("R", -5.0), ("W", 0.0), ("B", 5.0))]         # red on the viewer's left
    pony = F.prism_cutter("GasCap_Pony", "+X", pony_at(gy, gz - 8.0, 55.0, -1), top - 0.2, top + 0.03)
    parts.append((F.prism_cutter("GasCap", "+X", F.circle(gy, gz, gr - FIT / SCALE, 48), f, top), [face] + bars + [pony], [ring]))
    return parts


def bumper_parts(tree, skin=None):
    """[(bumper, union pieces, cut pieces)]. tree: the skin the bumpers hug, before the quarters tuck under; the
    rear one stands GAP clear of the finished `skin` (the tuck relaxes the skin under its bottom edge too)."""
    half = math.pi / 2
    # the full blade wraps round the corners, then thins over 2.5 mm of the side run to hug the fenders
    # closely; the tips round off from below, blunt (the top stays flat: it is the print bed)
    front = _bumper("Bumper_F", tree, "-X", FRONT_BUMPER_Z, FRONT_WRAP_END_X, half, 3 * half, FRONT_GUARDS,
                    side_thin=True, side_ramp=2.5, min_t=FRONT_BUMPER_SIDE_T, end_gap=0.0, end_fade=0.08, end_height=0.5,
                    path_smooth=30)
    rear = _bumper("Bumper_R", tree, "+X", REAR_BUMPER_Z, REAR_BUMPER_CENTER_X, -REAR_BUMPER_WRAP, REAR_BUMPER_WRAP,
                   REAR_GUARDS, rise=rear_bumper_rise, face_rise=rear_bumper_face_rise, bottom=rear_bumper_bottom,
                   profile=REAR_BUMPER_PROFILE, end_fade=0.0, end_round=1.0, min_t=0.5, end_gap=0.0, step=0.25,
                   cast_dir=Vector((1.0, 0.0, 0.0)), curl=lambda p: rear_bumper_curl(p.y / SCALE), clear=skin)
    ny0, nz0, ny1, nz1 = PLATE_NOTCH
    notch = F.prism_cutter("Bumper_R_PlateNotch", "+X", F.rounded_poly([(ny0, nz0), (ny1, nz0), (ny1, nz1), (ny0, nz1)], [0, 0, 15, 15]),
                           4300 * SCALE, 4800 * SCALE)
    pieces = rear[1]
    # plate lamp housing under the top of the notch, and two domed bolt heads on the face
    pieces.append(F.prism_cutter("Bumper_R_PlateLamp", "+X", rect(-22.0, nz1 - 14.0, 22.0, nz1 + 4.0, 4.0), 4515 * SCALE, 4560 * SCALE))
    bvh = F._bvh(rear[0].data)                    # not linked yet: use its mesh directly
    pieces += [bolt_head(f"Bumper_R_Bolt{'L' if y < 0 else 'R'}", bvh, y, z) for y, z in REAR_BOLTS]
    return [front + ([],), rear + ([notch],)]


def bolt_head(name, tree, y, z):
    """A round bolt head on the rear bumper's face at (y, z) (real mm): a dome BOLT_R round rising BOLT_H
    with an elliptical profile like the lamp lenses (its foot square to the face, so it shows a dark edge
    round a bright crown, as on the car), lofted along the face's normal there on a short skirt sunk into
    the face so the union closes where the face curves away under the foot."""
    hit, normal, *_ = tree.ray_cast(Vector((5000 * SCALE, y * SCALE, z * SCALE)), Vector((-1.0, 0.0, 0.0)), 100.0)
    if hit is None:
        raise ValueError(f"bumper bolt at ({y:.0f}, {z:.0f}) misses the bumper")
    n = normal.normalized() if normal.x > 0 else -normal.normalized()
    sections = [(F.circle(0.0, 0.0, BOLT_R, 32), -5.0 * SCALE)]
    for k in range(9):
        a = math.pi / 2 * 0.95 * k / 8
        sections.append((F.circle(0.0, 0.0, BOLT_R * math.cos(a), 32), BOLT_H * math.sin(a) * SCALE))
    ob = F.loft_solid(name, "+Z", sections)
    ob.data.transform(Matrix.Translation(hit) @ n.to_track_quat('Z', 'Y').to_matrix().to_4x4())
    return ob


# ---------------------------------------------------------------- chassis

CHASSIS_Z0 = 255.0        # underside of the chassis plate (real mm above ground)
CHASSIS_X0, CHASSIS_X1, CHASSIS_Y = 350.0, 3600.0, 590.0      # ends just behind the rear axle boss
DIFF = (3535.0, 338.0, 120.0)            # differential housing on the rear axle: x, z, radius (flat underside)
BOSS_HALF_X, BOSS_TOP = 60.0, 390.0     # axle bosses rise into slots in the body bottom
SLOT_CLEAR = 0.15                        # print mm per side
# exhaust: separate chrome tips under the rear valance, each hung from the floor by a fin pushed
# into a slot; printed standing on the pipe's front end (the fin's lower edge is 45 degrees)
# the tip's wall round its open bore is 12 mm (0.5 mm printed): thinner, the slicer drops it
EXHAUST_Y, EXHAUST_R, EXHAUST_TIP_R, EXHAUST_BORE_R = 450.0, 28.0, 33.0, 21.0
EXHAUST_Z = REAR_FLOOR_Z - 8.0 - EXHAUST_R
EXHAUST_X0, EXHAUST_X1 = 3880.0, 4400.0
EXHAUST_FIN = [(4080.0 - (REAR_FLOOR_Z + 65.0 - EXHAUST_Z), EXHAUST_Z), (4080.0, REAR_FLOOR_Z + 65.0),
               (4150.0, REAR_FLOOR_Z + 65.0), (4150.0, EXHAUST_Z)]             # leading edge at 45 degrees
EXHAUST_FIN_T = 20.0
AXLE_HOLE_R = 1.4                        # 2.3 mm octagonal axle (2.49 over corners) spins in a 2.8 mm hole


def chassis_slots():
    """[(name, cutter)] transverse slots in the body bottom that the chassis axle bosses key into."""
    from body import FRONT_AXLE_X, REAR_AXLE_X, Z_BOTTOM
    c = SLOT_CLEAR / SCALE
    return [(f"Cut_BossSlot{tag}", F.prism_cutter(
        f"Cut_BossSlot{tag}", "+Z", rect(ax - BOSS_HALF_X - c, -CHASSIS_Y - 26 - c, ax + BOSS_HALF_X + c, CHASSIS_Y + 26 + c, 8),
        Z_BOTTOM * SCALE - 2.0, BOSS_TOP * SCALE + SLOT_CLEAR)) for tag, ax in (("F", FRONT_AXLE_X), ("R", REAR_AXLE_X))]


def chassis_parts():
    """Black chassis plate, inset well inside the rockers so the body stands clear of the ground.

    Returns (plate, unions, plate_cuts). The plate's top mates with the body's flat bottom; two
    bosses carrying the axle holes key into the slots from chassis_slots()."""
    from body import FRONT_AXLE_X, REAR_AXLE_X, WHEEL_RADIUS, Z_BOTTOM
    plate = F.prism_cutter("Chassis", "+Z", rect(CHASSIS_X0, -CHASSIS_Y, CHASSIS_X1, CHASSIS_Y, 60),
                           CHASSIS_Z0 * SCALE, Z_BOTTOM * SCALE)
    unions, plate_cuts = [], []
    for tag, ax in (("F", FRONT_AXLE_X), ("R", REAR_AXLE_X)):
        unions.append(F.prism_cutter(f"Chassis_Boss{tag}", "+Z", rect(ax - BOSS_HALF_X, -CHASSIS_Y, ax + BOSS_HALF_X, CHASSIS_Y, 8),
                                     Z_BOTTOM * SCALE - 0.2, BOSS_TOP * SCALE))
        plate_cuts.append(F.loft_solid(f"Cut_ChassisAxle{tag}", "-Y", [
            (F.circle(ax, WHEEL_RADIUS, AXLE_HOLE_R / SCALE, 24), -40.0), (F.circle(ax, WHEEL_RADIUS, AXLE_HOLE_R / SCALE, 24), 40.0)]))
    dx, dz, dr = DIFF
    unions.append(F.loft_solid("Chassis_Diff", "+X", [
        (F.circle(0.0, dz, dr * math.sin(math.radians(a)), 24), (dx - dr * math.cos(math.radians(a))) * SCALE)
        for a in (12, 35, 60, 90, 120, 145, 168)]))
    plate_cuts.append(F.prism_cutter("Chassis_DiffFlat", "+Z", rect(dx - dr - 20, -dr - 20, dx + dr + 20, dr + 20, 0),
                                     (CHASSIS_Z0 - 100.0) * SCALE, CHASSIS_Z0 * SCALE))
    return plate, unions, plate_cuts


def diff_cover():
    """The differential housing's underside, below the chassis plate: a black dome glued on under
    the plate (printed flat side down), so the round housing shows below the car."""
    dx, dz, dr = DIFF
    rings = []
    for k in range(7):
        z = CHASSIS_Z0 - (CHASSIS_Z0 - (dz - dr) - 2.0) * k / 6     # stop 2 mm short of the pole: a small flat
        rings.append((F.circle(dx, 0.0, math.sqrt(dr * dr - (dz - z) ** 2), 32), z * SCALE))
    return F.loft_solid("DiffCover", "+Z", rings)


def exhaust_slots():
    """[(name, cutter)] slots in the rear floor for the exhaust tips' fins."""
    c = SLOT_CLEAR / SCALE
    t = EXHAUST_FIN_T / 2 + c
    (ax, az), (bx, bz) = EXHAUST_FIN[0], EXHAUST_FIN[1]           # where the fin's leading edge meets the floor
    x0, x1 = ax + (bx - ax) * (REAR_FLOOR_Z - az) / (bz - az) - c, EXHAUST_FIN[2][0] + c
    return [(f"Cut_ExhaustSlot_{'L' if s < 0 else 'R'}", F.prism_cutter(
        f"Cut_ExhaustSlot_{'L' if s < 0 else 'R'}", "+Y", rect(x0, REAR_FLOOR_Z - 20.0, x1, EXHAUST_FIN[1][1] + c, 0),
        (s * EXHAUST_Y - t) * SCALE, (s * EXHAUST_Y + t) * SCALE)) for s in (-1, 1)]


def exhaust_parts():
    """[(part, union pieces, cut pieces)] chrome tailpipes: pipe, a turndown tip (a sleeve over the
    pipe, its last stretch bent down 45 degrees) with an open dark bore, and the hanger fin."""
    parts = []
    z = EXHAUST_Z
    for s in (-1, 1):
        tag, y = ("L" if s < 0 else "R"), s * EXHAUST_Y
        pipe = F.tube(f"Exhaust_{tag}", [(EXHAUST_X0, y, z), (EXHAUST_X1 - 60.0, y, z)], EXHAUST_R, 24)
        tip = F.tube(f"Exhaust_{tag}_Tip", [(EXHAUST_X1 - 70.0, y, z), (EXHAUST_X1 - 5.0, y, z), (EXHAUST_X1 + 22.0, y, z - 27.0)],
                     EXHAUST_TIP_R, 24)
        bore = F.tube(f"ExhaustBore_{tag}", [(EXHAUST_X1 - 40.0, y, z), (EXHAUST_X1 - 5.0, y, z), (EXHAUST_X1 + 50.0, y, z - 55.0)],
                      EXHAUST_BORE_R, 24)
        fin = F.prism_cutter(f"Exhaust_{tag}_Fin", "+Y", EXHAUST_FIN, (y - EXHAUST_FIN_T / 2) * SCALE, (y + EXHAUST_FIN_T / 2) * SCALE)
        parts.append((pipe, [tip, fin], [bore]))
    return parts


def backup_radius(r, x):
    """Radius at x (real mm) of a backup-lamp housing r round at the face: the cone, then the spigot."""
    return r + BACKUP_FLARE * (BACKUP_FACE_X - max(x, BACKUP_SPIGOT_X))


def backup_light_parts():
    """[(part, union pieces, cut pieces)] chrome backup lamps: housings flaring back from a vertical face
    into the valance, their spigots slid into the sockets from behind, printed standing on their flat
    backs. The face's edge rounds over onto the bezel's crest; inside it the well falls to the lens seat
    and the domed lens fills it (the well first, then the lens). The lens and the well's slope are glass;
    the part carries its axis for the lens material's rings."""
    parts = []
    face, e = BACKUP_FACE_X * SCALE, BACKUP_EDGE_R
    seat = face - BACKUP_LENS_DEPTH
    for y, z, r in BACKUP_LIGHTS:
        tag = "L" if y < 0 else "R"
        sections = [(F.circle(y, z, backup_radius(r, x), 48), x * SCALE) for x in (BACKUP_BACK_X, BACKUP_SPIGOT_X)]
        for k in range(7):                       # the outer edge rounds over onto the crest
            a = math.pi / 2 * k / 6
            sections.append((F.circle(y, z, r - e + e * math.cos(a), 48), face - (e - e * math.sin(a)) * SCALE))
        can = F.loft_solid(f"BackupLight_{tag}", "+X", sections)
        can["lens_axis"] = (0.0, y * SCALE, z * SCALE)
        slope = (BACKUP_CREST_R - BACKUP_LENS_R) / BACKUP_LENS_DEPTH          # real mm of radius per print mm of depth
        well = F.loft_solid(f"BackupLens_{tag}_Well", "+X", [(F.circle(y, z, BACKUP_LENS_R, 48), seat),
                                                             (F.circle(y, z, BACKUP_CREST_R + slope * 0.5, 48), face + 0.5)])
        rf = BACKUP_LENS_R + 0.8                 # the dome's foot reaches just under the well's slope
        sections = [(F.circle(y, z, rf, 48), seat - 0.1)]
        for k in range(9):
            a = math.pi / 2 * 0.95 * k / 8
            sections.append((F.circle(y, z, rf * math.cos(a), 48), seat + BACKUP_LENS_DOME * math.sin(a)))
        parts.append((can, [F.loft_solid(f"BackupLens_{tag}", "+X", sections)], [well]))
    return parts


# ---------------------------------------------------------------- side mirrors

MIRROR_SIDES = (-1,)                            # the car in the photos has only the driver's (left) mirror
MIRROR_X0, MIRROR_X1 = 1986.0, 2014.0          # fore-aft thickness of the flat mirror part (~1.17 mm), just behind the vent post
MIRROR_REF_Z = (858.0, 904.0)                   # u is measured outboard from the door's side skin over this band
# the base sits on the door's rolled top, its underside following the surface from z0 up to z1 and
# its top flat at z2; a peg drops from it into a slot in the door top. The stalk rises out and up to
# a rectangular head above the sill (a little taller at its outboard end), its back domed forward.
MIRROR_BASE_Z = (888.0, 912.0, 926.0)
MIRROR_PEG = (-70.0, -56.0, 862.0)              # u0, u1, bottom z
MIRROR_ARM = ((-60.0, 916.0), (-22.0, 972.0), 11.0)
MIRROR_HEAD = [(-15.0, 970.0), (95.0, 962.0), (95.0, 1040.0), (-15.0, 1028.0)]   # (u, z) corners
MIRROR_HEAD_R, MIRROR_DOME = 16.0, 17.0
MIRROR_GAP = 0.15                               # print mm between the base and the door


def _door_skin_y(tree, z0, z1):
    """Outermost door-skin y (real mm, right side) over the mirror's fore-aft span, between heights z0 and z1."""
    best = 0.0
    for k in range(7):
        z = z0 + (z1 - z0) * k / 6
        for x in (MIRROR_X0, MIRROR_X1):
            best = max(best, hit_w(tree, "+Y", x, z) / SCALE)
    return best


def _mirror_skin(tree):
    return _door_skin_y(tree, *MIRROR_REF_Z)


def _door_top_u(tree, skin, z):
    """How far outboard of the reference skin (real mm, negative = inboard) the door's rolled top is at
    height z, over the mirror's fore-aft span."""
    return max(hit_w(tree, "+Y", x, z) / SCALE for x in (MIRROR_X0, MIRROR_X1)) - skin


def _mirror_peg(skin):
    pu0, pu1, pz0 = MIRROR_PEG
    return pu0, pz0, pu1, MIRROR_BASE_Z[1] + 4.0


def mirror_slots(tree):
    """[(name, cutter)] slots in the door tops for the mirror pegs (doors.py cuts them into the doors):
    the peg's profile, a FIT larger, run fore-aft through the mirror's span."""
    skin = _mirror_skin(tree)
    pu0, pz0, pu1, pz1 = _mirror_peg(skin)
    c = FIT / SCALE
    slots = []
    for side in MIRROR_SIDES:
        tag = "L" if side < 0 else "R"
        outline = [(side * (skin + u), z) for u, z in rect(pu0 - c, pz0 - c, pu1 + c, pz1 + 40.0, 0)]
        slots.append((f"Cut_MirrorSlot_{tag}", F.prism_cutter(f"Cut_MirrorSlot_{tag}", "+X", outline,
                                                             (MIRROR_X0 - c) * SCALE, (MIRROR_X1 + c) * SCALE)))
    return slots


def mirror_parts(tree):
    """[(part, union_pieces)] chrome door mirrors.

    Each mirror is a flat profile (base, peg, stalk, head) extruded fore-aft, with the head's back
    domed forward, so it prints on its flat rear face, dome up, without supports."""
    skin = _mirror_skin(tree)
    w0, w1 = MIRROR_X0 * SCALE, MIRROR_X1 * SCALE
    g = MIRROR_GAP / SCALE
    z0, z1, z2 = MIRROR_BASE_Z
    under = [(_door_top_u(tree, skin, z) + g, z + g) for z in (z0 + (z1 - z0) * k / 8 for k in range(9))]
    base_outline = under + [(under[-1][0], z2), (under[0][0], z2)]
    parts = []
    for side in MIRROR_SIDES:
        tag = "L" if side < 0 else "R"

        def place(outline):          # (u outboard, z) -> (y, z) on this side
            return [(side * (skin + u), z) for u, z in outline]

        base = F.prism_cutter(f"Mirror_{tag}", "+X", place(base_outline), w0, w1)
        peg = F.prism_cutter(f"Mirror_{tag}_Peg", "+X", place(rect(*_mirror_peg(skin), 0)), w0, w1)
        (a, b, r) = MIRROR_ARM
        arm = [F.prism_cutter(f"Mirror_{tag}_Arm{k}", "+X", place(o), w0, w1) for k, o in enumerate(capsule_chain([a, b], r))]
        outline = place(F.rounded_poly(MIRROR_HEAD, MIRROR_HEAD_R))
        head = F.prism_cutter(f"Mirror_{tag}_Head", "+X", outline, w0, w1)
        # the back: the outline shrinking toward its centre as it domes forward (it starts a hair inside the rim)
        cu, cz = (sum(c) / len(outline) for c in zip(*outline))
        back = [([(cu + (u - cu) * k, cz + (z - cz) * k) for u, z in outline], w0 + 0.05 - MIRROR_DOME * SCALE * math.sin(a))
                for a in (math.pi / 2 * 0.9 * j / 7 for j in range(8)) for k in [0.99 - 0.7 * (1 - math.cos(a))]]
        head_back = F.loft_solid(f"Mirror_{tag}_Back", "+X", back)
        parts.append((base, arm + [head, head_back, peg]))
    return parts
