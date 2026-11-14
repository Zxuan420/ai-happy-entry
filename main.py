import struct
import zlib
import math
import os

class PixelBuffer:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4) # RGBA

    def set_pixel(self, x, y, r, g, b, a=255):
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 4
            if a == 255:
                self.pixels[idx] = max(0, min(255, int(r)))
                self.pixels[idx+1] = max(0, min(255, int(g)))
                self.pixels[idx+2] = max(0, min(255, int(b)))
                self.pixels[idx+3] = 255
            elif a > 0:
                fa = a / 255.0
                inv_fa = 1.0 - fa
                or_ = self.pixels[idx]
                og_ = self.pixels[idx+1]
                ob_ = self.pixels[idx+2]
                oa_ = self.pixels[idx+3] / 255.0
                
                nr = r * fa + or_ * inv_fa
                ng = g * fa + og_ * inv_fa
                nb = b * fa + ob_ * inv_fa
                na = fa + oa_ * inv_fa

                self.pixels[idx] = max(0, min(255, int(nr)))
                self.pixels[idx+1] = max(0, min(255, int(ng)))
                self.pixels[idx+2] = max(0, min(255, int(nb)))
                self.pixels[idx+3] = max(0, min(255, int(na * 255)))

    def blend_pixel(self, x, y, r, g, b, a):
        self.set_pixel(x, y, r, g, b, a)

def write_chunk(f, tag, data):
    f.write(struct.pack("!I", len(data)))
    f.write(tag)
    f.write(data)
    crc = zlib.crc32(tag)
    crc = zlib.crc32(data, crc)
    f.write(struct.pack("!I", crc & 0xFFFFFFFF))

def encode_png(pixel_buffer, filepath):
    w = pixel_buffer.width
    h = pixel_buffer.height
    
    # Build raw scanlines with filter type 0 (None)
    row_stride = w * 4
    raw_data = bytearray()
    for y in range(h):
        raw_data.append(0) # filter byte: None
        start = y * row_stride
        raw_data.extend(pixel_buffer.pixels[start:start+row_stride])
        
    compressed = zlib.compress(raw_data, level=6)
    
    with open(filepath, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        write_chunk(f, b"IHDR", struct.pack("!IIBBBBB", w, h, 8, 6, 0, 0, 0))
        write_chunk(f, b"IDAT", compressed)
        write_chunk(f, b"IEND", b"")

# Rasterizer helpers
def draw_line(buf, x0, y0, x1, y1, r, g, b, a=255):
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    
    cx, cy = x0, y0
    while True:
        buf.set_pixel(cx, cy, r, g, b, a)
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy

def fill_circle(buf, xc, yc, radius, r, g, b, a=255):
    r_sq = radius * radius
    min_x = max(0, int(xc - radius))
    max_x = min(buf.width - 1, int(xc + radius))
    min_y = max(0, int(yc - radius))
    max_y = min(buf.height - 1, int(yc + radius))
    
    for y in range(min_y, max_y + 1):
        dy = y - yc
        dy_sq = dy * dy
        for x in range(min_x, max_x + 1):
            dx = x - xc
            if dx * dx + dy_sq <= r_sq:
                buf.set_pixel(x, y, r, g, b, a)

def fill_ellipse(buf, xc, yc, rx, ry, r, g, b, a=255):
    if rx <= 0 or ry <= 0:
        return
    min_x = max(0, int(xc - rx))
    max_x = min(buf.width - 1, int(xc + rx))
    min_y = max(0, int(yc - ry))
    max_y = min(buf.height - 1, int(yc + ry))
    
    rx_sq = rx * rx
    ry_sq = ry * ry
    
    for y in range(min_y, max_y + 1):
        dy = y - yc
        dy_term = (dy * dy) / ry_sq
        if dy_term > 1.0:
            continue
        dx_limit = rx * math.sqrt(1.0 - dy_term)
        x_start = max(min_x, int(xc - dx_limit))
        x_end = min(max_x, int(xc + dx_limit))
        for x in range(x_start, x_end + 1):
            buf.set_pixel(x, y, r, g, b, a)

def fill_polygon(buf, points, r, g, b, a=255):
    if not points:
        return
    min_y = max(0, int(min(p[1] for p in points)))
    max_y = min(buf.height - 1, int(max(p[1] for p in points)))
    min_x = max(0, int(min(p[0] for p in points)))
    max_x = min(buf.width - 1, int(max(p[0] for p in points)))
    
    n = len(points)
    for y in range(min_y, max_y + 1):
        nodes = []
        j = n - 1
        for i in range(n):
            xi, yi = points[i]
            xj, yj = points[j]
            if (yi < y and yj >= y) or (yj < y and yi >= y):
                if yi != yj:
                    x_intersect = xi + (y - yi) / (yj - yi) * (xj - xi)
                    nodes.append(x_intersect)
            j = i
        nodes.sort()
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                x_start = max(min_x, int(math.ceil(nodes[i])))
                x_end = min(max_x, int(math.floor(nodes[i+1])))
                for x in range(x_start, x_end + 1):
                    buf.set_pixel(x, y, r, g, b, a)

def fill_rounded_rect(buf, x, y, w, h, radius, r, g, b, a=255):
    radius = max(0, min(radius, min(w, h) // 2))
    # Fill central cross and rectangles
    fill_polygon(buf, [
        (x + radius, y),
        (x + w - radius, y),
        (x + w - radius, y + h),
        (x + radius, y + h)
    ], r, g, b, a)
    fill_polygon(buf, [
        (x, y + radius),
        (x + radius, y + radius),
        (x + radius, y + h - radius),
        (x, y + h - radius)
    ], r, g, b, a)
    fill_polygon(buf, [
        (x + w - radius, y + radius),
        (x + w, y + radius),
        (x + w, y + h - radius),
        (x + w - radius, y + h - radius)
    ], r, g, b, a)
    
    # 4 corners
    fill_circle(buf, x + radius, y + radius, radius, r, g, b, a)
    fill_circle(buf, x + w - radius, y + radius, radius, r, g, b, a)
    fill_circle(buf, x + radius, y + h - radius, radius, r, g, b, a)
    fill_circle(buf, x + w - radius, y + h - radius, radius, r, g, b, a)

def draw_vertical_gradient(buf, color_top, color_bottom):
    h = buf.height
    w = buf.width
    r1, g1, b1 = color_top
    r2, g2, b2 = color_bottom
    for y in range(h):
        t = y / max(1, h - 1)
        r = r1 * (1 - t) + r2 * t
        g = g1 * (1 - t) + g2 * t
        b = b1 * (1 - t) + b2 * t
        for x in range(w):
            buf.set_pixel(x, y, r, g, b, 255)

def draw_radial_glow(buf, xc, yc, max_radius, color, max_alpha=255):
    min_x = max(0, int(xc - max_radius))
    max_x = min(buf.width - 1, int(xc + max_radius))
    min_y = max(0, int(yc - max_radius))
    max_y = min(buf.height - 1, int(yc + max_radius))
    
    cr, cg, cb = color
    for y in range(min_y, max_y + 1):
        dy = y - yc
        for x in range(min_x, max_x + 1):
            dx = x - xc
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= max_radius:
                t = 1.0 - (dist / max_radius)
                alpha = int(max_alpha * (t * t))
                if alpha > 0:
                    buf.blend_pixel(x, y, cr, cg, cb, alpha)

# Scene drawing code
def draw_scene(buf):
    # 1. Sky gradient (peach at top to gold near horizon)
    draw_vertical_gradient(buf, (255, 182, 148), (255, 224, 158))
    
    # 4. Sun: warmer and more golden with larger, stronger soft glow
    sun_x, sun_y = 280, 290
    draw_radial_glow(buf, sun_x, sun_y, 320, (255, 215, 130), 220)
    draw_radial_glow(buf, sun_x, sun_y, 180, (255, 190, 80), 240)
    fill_circle(buf, sun_x, sun_y, 75, 255, 230, 100, 255)

    # Soft golden sparkle dots in the air near the sun
    sparkles = [
        (220, 240), (340, 220), (190, 310), (370, 330), (250, 180), (310, 380), (280, 200)
    ]
    for sp_x, sp_y in sparkles:
        fill_circle(buf, sp_x, sp_y, 4, 255, 250, 200, 200)
        fill_circle(buf, sp_x, sp_y, 2, 255, 255, 255, 240)

    # 5. Rainbow: raise saturation slightly so bands are visible but soft
    rainbow_colors = [
        (255, 120, 120), (255, 170, 100), (255, 240, 100),
        (120, 240, 120), (100, 180, 255), (180, 120, 255)
    ]
    rc_x, rc_y = 512, 700
    r_base = 450
    for i, col in enumerate(rainbow_colors):
        r_inner = r_base + i * 10
        r_outer = r_inner + 9
        r_in_sq = r_inner * r_inner
        r_out_sq = r_outer * r_outer
        for y in range(0, 650):
            dy = y - rc_y
            dy_sq = dy * dy
            for x in range(0, 1024):
                dx = x - rc_x
                d_sq = dx * dx + dy_sq
                if r_in_sq <= d_sq <= r_out_sq:
                    buf.blend_pixel(x, y, col[0], col[1], col[2], 85)

    # Puffy white clouds
    clouds = [
        (180, 180, 90, 40),
        (750, 220, 120, 50),
        (480, 140, 100, 45)
    ]
    for cx, cy, cw, ch in clouds:
        fill_ellipse(buf, cx, cy, cw, ch, 255, 255, 255, 210)
        fill_ellipse(buf, cx - int(cw*0.5), cy + int(ch*0.2), int(cw*0.6), int(ch*0.7), 255, 255, 255, 190)
        fill_ellipse(buf, cx + int(cw*0.5), cy + int(ch*0.2), int(cw*0.6), int(ch*0.7), 255, 255, 255, 190)

    # Two soft rolling green hills
    back_points = [(0, 620)]
    for x in range(0, 1030, 20):
        y_val = 620 - int(60 * math.sin(x * 0.004 + 1.2) + 40 * math.cos(x * 0.008))
        back_points.append((x, y_val))
    back_points.extend([(1024, 1024), (0, 1024)])
    fill_polygon(buf, back_points, 124, 185, 110, 255)

    front_points = [(0, 720)]
    for x in range(0, 1030, 20):
        y_val = 720 - int(70 * math.cos(x * 0.005) + 30 * math.sin(x * 0.01))
        front_points.append((x, y_val))
    front_points.extend([(1024, 1024), (0, 1024)])
    fill_polygon(buf, front_points, 84, 153, 90, 255)

    # Fill empty foreground: scatter many small white/yellow flowers and grass tufts across front hill
    for fx in range(30, 1010, 35):
        fy = 720 - int(70 * math.cos(fx * 0.005) + 30 * math.sin(fx * 0.01)) + ((fx * 7) % 18)
        # Grass tufts
        draw_line(buf, fx, fy, fx - 4, fy - 14, 50, 110, 60, 255)
        draw_line(buf, fx, fy, fx + 4, fy - 16, 65, 130, 75, 255)
        if fx % 70 == 0:
            # Yellow flower
            fill_circle(buf, fx, fy - 18, 5, 255, 230, 100, 255)
            fill_circle(buf, fx, fy - 18, 2, 255, 255, 200, 255)
        elif fx % 50 == 0:
            # White flower
            fill_circle(buf, fx, fy - 16, 5, 245, 245, 255, 255)
            fill_circle(buf, fx, fy - 16, 2, 255, 220, 100, 255)

    # Back hill grass details and flowers
    for fx in range(50, 1000, 75):
        fy = 620 - int(60 * math.sin(fx * 0.004 + 1.2) + 40 * math.cos(fx * 0.008)) + ((fx * 3) % 15)
        draw_line(buf, fx, fy, fx, fy - 11, 90, 150, 90, 255)
        fill_circle(buf, fx, fy - 13, 4, 255, 240, 180, 255)

    # 3. Sunflower: tall one + second SMALL sunflower sprout ("baby" sunflower) beside it
    sprout_x, sprout_y = 380, 730
    # Thicker stem
    fill_rounded_rect(buf, sprout_x - 6, sprout_y - 180, 12, 180, 4, 82, 150, 70, 255)
    # Bigger leaves
    fill_ellipse(buf, sprout_x - 45, sprout_y - 90, 50, 18, 102, 176, 85, 255)
    fill_ellipse(buf, sprout_x + 45, sprout_y - 90, 50, 18, 102, 176, 85, 255)

    # Sunflower head at top of stem
    sf_x, sf_y = sprout_x, sprout_y - 200
    for angle_deg in range(0, 360, 20):
        rad = math.radians(angle_deg)
        px = sf_x + int(50 * math.cos(rad))
        py = sf_y + int(50 * math.sin(rad))
        fill_ellipse(buf, px, py, 26, 14, 255, 210, 50, 255)
    # Brown center
    fill_circle(buf, sf_x, sf_y, 42, 115, 70, 35, 255)
    fill_circle(buf, sf_x - 6, sf_y - 6, 12, 145, 90, 50, 255)

    # Baby sunflower beside the tall one
    baby_x, baby_y = sprout_x + 75, sprout_y - 30
    fill_rounded_rect(buf, baby_x - 4, baby_y - 90, 8, 90, 3, 82, 150, 70, 255)
    fill_ellipse(buf, baby_x - 22, baby_y - 45, 25, 10, 102, 176, 85, 255)
    baby_head_x, baby_head_y = baby_x, baby_y - 105
    for angle_deg in range(0, 360, 30):
        rad = math.radians(angle_deg)
        px = baby_head_x + int(28 * math.cos(rad))
        py = baby_head_y + int(28 * math.sin(rad))
        fill_ellipse(buf, px, py, 16, 9, 255, 220, 60, 255)
    fill_circle(buf, baby_head_x, baby_head_y, 22, 125, 75, 40, 255)

    # Ladybug on leaf
    lb_x, lb_y = sprout_x - 55, sprout_y - 92
    fill_ellipse(buf, lb_x, lb_y, 9, 7, 220, 50, 50, 255)
    fill_circle(buf, lb_x - 3, lb_y, 3, 30, 30, 30, 255)
    fill_circle(buf, lb_x + 3, lb_y - 2, 2, 30, 30, 30, 255)
    fill_circle(buf, lb_x + 3, lb_y + 2, 2, 30, 30, 30, 255)

    # Three butterflies in the air
    butterflies = [
        (sf_x - 85, sf_y - 30),
        (210, 470),
        (830, 490)
    ]
    for bf_x, bf_y in butterflies:
        fill_ellipse(buf, bf_x - 12, bf_y - 9, 14, 9, 255, 160, 200, 220)
        fill_ellipse(buf, bf_x + 12, bf_y - 9, 14, 9, 255, 160, 200, 220)
        fill_ellipse(buf, bf_x - 10, bf_y + 9, 11, 8, 255, 200, 120, 220)
        fill_ellipse(buf, bf_x + 10, bf_y + 9, 11, 8, 255, 200, 120, 220)
        draw_line(buf, bf_x, bf_y - 14, bf_x, bf_y + 14, 50, 50, 50, 255)

    # Hero Robot (Centre-Right, LARGE, ~300px wide)
    bot_cx, bot_cy = 680, 650
    
    # Robot Body (rounded rect)
    fill_rounded_rect(buf, bot_cx - 110, bot_cy - 20, 220, 180, 40, 245, 242, 235, 255)
    fill_rounded_rect(buf, bot_cx - 70, bot_cy + 10, 140, 90, 20, 210, 230, 235, 255)
    fill_circle(buf, bot_cx, bot_cy + 55, 12, 255, 140, 140, 255)

    # Robot Head (large round)
    head_cy = bot_cy - 110
    fill_circle(buf, bot_cx, head_cy, 95, 245, 242, 235, 255)
    
    # Antenna on top of head
    draw_line(buf, bot_cx, head_cy - 95, bot_cx, head_cy - 135, 180, 180, 180, 255)
    draw_radial_glow(buf, bot_cx, head_cy - 135, 25, (255, 240, 150), 200)
    fill_circle(buf, bot_cx, head_cy - 135, 10, 255, 220, 80, 255)

    # Big friendly eyes
    fill_ellipse(buf, bot_cx - 35, head_cy - 10, 22, 28, 50, 60, 75, 255)
    fill_circle(buf, bot_cx - 28, head_cy - 18, 8, 255, 255, 255, 255)
    fill_circle(buf, bot_cx - 40, head_cy + 2, 4, 255, 255, 255, 255)
    
    fill_ellipse(buf, bot_cx + 35, head_cy - 10, 22, 28, 50, 60, 75, 255)
    fill_circle(buf, bot_cx + 42, head_cy - 18, 8, 255, 255, 255, 255)
    fill_circle(buf, bot_cx + 30, head_cy + 2, 4, 255, 255, 255, 255)

    # Soft pink blush circles on cheeks for warmth
    fill_circle(buf, bot_cx - 52, head_cy + 12, 14, 255, 165, 175, 190)
    fill_circle(buf, bot_cx + 52, head_cy + 12, 14, 255, 165, 175, 190)

    # 1. Mouth: slightly bigger and warmer upward smile
    for sx_off in range(-18, 19):
        sy_off = int(26 - 0.035 * (sx_off * sx_off))
        buf.set_pixel(bot_cx + sx_off, head_cy + sy_off, 60, 70, 85, 255)
        buf.set_pixel(bot_cx + sx_off, head_cy + sy_off + 1, 60, 70, 85, 255)
        buf.set_pixel(bot_cx + sx_off, head_cy + sy_off + 2, 60, 70, 85, 255)

    # Arms
    fill_rounded_rect(buf, bot_cx - 155, bot_cy + 25, 45, 22, 10, 225, 222, 215, 255)
    fill_circle(buf, bot_cx - 155, bot_cy + 36, 12, 235, 232, 225, 255)

    fill_rounded_rect(buf, bot_cx + 110, bot_cy + 30, 45, 22, 10, 225, 222, 215, 255)
    fill_circle(buf, bot_cx + 155, bot_cy + 41, 12, 235, 232, 225, 255)

    # Robot wheels / base tracks
    fill_rounded_rect(buf, bot_cx - 90, bot_cy + 150, 180, 35, 15, 80, 90, 105, 255)
    fill_circle(buf, bot_cx - 60, bot_cy + 167, 12, 50, 55, 65, 255)
    fill_circle(buf, bot_cx + 60, bot_cy + 167, 12, 50, 55, 65, 255)

    # 1. Watering Can: BIGGER classic watering can, handle on top, long spout angled up-left ending in flared rose head pointing at sunflower
    wc_x, wc_y = bot_cx - 170, bot_cy - 10
    # Watering can body (larger rounded rect)
    fill_rounded_rect(buf, wc_x - 55, wc_y - 35, 95, 75, 24, 70, 140, 200, 255)
    # Handle on top
    fill_rounded_rect(buf, wc_x - 12, wc_y - 68, 42, 36, 12, 90, 160, 220, 255)
    
    # Spout angled up-left toward sunflower
    fill_polygon(buf, [
        (470, 615),
        (478, 630),
        (395, 520),
        (385, 508)
    ], 70, 140, 200, 255)
    # Flared rose (sprinkler head) at tip
    fill_ellipse(buf, 390, 514, 8, 14, 90, 160, 220, 255)

    # Clear ARC of BIGGER light-blue water droplets (9 larger dots falling from rose head down onto sunflower)
    air_droplets = [
        (390, 514),
        (388, 511),
        (386, 510),
        (384, 511),
        (382, 514),
        (381, 518),
        (380, 522),
        (380, 526),
        (380, 530)
    ]
    for dx_p, dy_p in air_droplets:
        fill_circle(buf, dx_p, dy_p, 6, 130, 205, 255, 240)
        fill_circle(buf, dx_p, dy_p, 3, 210, 245, 255, 255)

    # Droplets on the petals
    petal_droplets = [
        (sf_x - 12, sf_y - 18),
        (sf_x + 15, sf_y + 12)
    ]
    for dx_p, dy_p in petal_droplets:
        fill_circle(buf, dx_p, dy_p, 3, 150, 220, 255, 255)

def main():
    width = 1024
    height = 1024
    buf = PixelBuffer(width, height)
    draw_scene(buf)
    
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")
    encode_png(buf, out_path)
    print(f"Successfully generated entry at {out_path}")

if __name__ == "__main__":
    main()



