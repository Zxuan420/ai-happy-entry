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
    
    row_stride = w * 4
    raw_data = bytearray()
    for y in range(h):
        raw_data.append(0)
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
    # 1. Sky gradient
    draw_vertical_gradient(buf, (255, 182, 148), (255, 224, 158))
    
    # 4. Sun: stronger, larger sun glow
    sun_x, sun_y = 260, 270
    draw_radial_glow(buf, sun_x, sun_y, 450, (255, 215, 130), 230)
    draw_radial_glow(buf, sun_x, sun_y, 240, (255, 190, 80), 250)
    fill_circle(buf, sun_x, sun_y, 85, 255, 230, 100, 255)

    # Soft golden sparkle dots near sun
    sparkles = [
        (200, 220), (320, 200), (170, 290), (350, 310), (230, 160), (290, 360), (260, 180)
    ]
    for sp_x, sp_y in sparkles:
        fill_circle(buf, sp_x, sp_y, 4, 255, 250, 200, 200)
        fill_circle(buf, sp_x, sp_y, 2, 255, 255, 255, 240)

    # 5. Rainbow
    rainbow_colors = [
        (255, 120, 120), (255, 170, 100), (255, 240, 100),
        (120, 240, 120), (100, 180, 255), (180, 120, 255)
    ]
    rc_x, rc_y = 512, 600
    r_base = 400
    for i, col in enumerate(rainbow_colors):
        r_inner = r_base + i * 10
        r_outer = r_inner + 9
        r_in_sq = r_inner * r_inner
        r_out_sq = r_outer * r_outer
        for y in range(0, 560):
            dy = y - rc_y
            dy_sq = dy * dy
            for x in range(0, 1024):
                dx = x - rc_x
                d_sq = dx * dx + dy_sq
                if r_in_sq <= d_sq <= r_out_sq:
                    buf.blend_pixel(x, y, col[0], col[1], col[2], 85)

    # Puffy white clouds
    clouds = [
        (160, 160, 90, 40),
        (780, 200, 120, 50),
        (480, 120, 100, 45)
    ]
    for cx, cy, cw, ch in clouds:
        fill_ellipse(buf, cx, cy, cw, ch, 255, 255, 255, 210)
        fill_ellipse(buf, cx - int(cw*0.5), cy + int(ch*0.2), int(cw*0.6), int(ch*0.7), 255, 255, 255, 190)
        fill_ellipse(buf, cx + int(cw*0.5), cy + int(ch*0.2), int(cw*0.6), int(ch*0.7), 255, 255, 255, 190)

    # 3. FILL THE FRAME: Move horizon UP (hills start higher, less empty grass at bottom)
    # Back hill (starts around y=420)
    back_points = [(0, 420)]
    for x in range(0, 1030, 20):
        y_val = 420 - int(45 * math.sin(x * 0.004 + 1.2) + 30 * math.cos(x * 0.008))
        back_points.append((x, y_val))
    back_points.extend([(1024, 1024), (0, 1024)])
    fill_polygon(buf, back_points, 124, 185, 110, 255)

    # Front hill (starts around y=520)
    front_points = [(0, 520)]
    for x in range(0, 1030, 20):
        y_val = 520 - int(55 * math.cos(x * 0.005) + 25 * math.sin(x * 0.01))
        front_points.append((x, y_val))
    front_points.extend([(1024, 1024), (0, 1024)])
    fill_polygon(buf, front_points, 84, 153, 90, 255)

    # Foreground flowers and grass tufts across front hill
    for fx in range(30, 1010, 30):
        fy = 520 - int(55 * math.cos(fx * 0.005) + 25 * math.sin(fx * 0.01)) + ((fx * 7) % 15)
        draw_line(buf, fx, fy, fx - 3, fy - 12, 50, 110, 60, 255)
        draw_line(buf, fx, fy, fx + 3, fy - 14, 65, 130, 75, 255)
        if fx % 60 == 0:
            fill_circle(buf, fx, fy - 15, 5, 255, 230, 100, 255)
            fill_circle(buf, fx, fy - 15, 2, 255, 255, 200, 255)
        elif fx % 40 == 0:
            fill_circle(buf, fx, fy - 14, 4, 245, 245, 255, 255)
            fill_circle(buf, fx, fy - 14, 2, 255, 220, 100, 255)

    # Back hill grass and flowers
    for fx in range(50, 1000, 70):
        fy = 420 - int(45 * math.sin(fx * 0.004 + 1.2) + 30 * math.cos(fx * 0.008)) + ((fx * 3) % 12)
        draw_line(buf, fx, fy, fx, fy - 10, 90, 150, 90, 255)
        fill_circle(buf, fx, fy - 11, 4, 255, 240, 180, 255)

    # 4. GOLDEN-HOUR WARMTH: Soft long shadow stretching from robot and sprout across grass away from sun (sun is at top-left, shadows stretch towards bottom-right)
    sprout_base_x, sprout_base_y = 360, 560
    shadow_points = [
        (sprout_base_x - 15, sprout_base_y),
        (sprout_base_x + 15, sprout_base_y),
        (sprout_base_x + 90, sprout_base_y + 40),
        (sprout_base_x + 60, sprout_base_y + 45)
    ]
    fill_polygon(buf, shadow_points, 55, 110, 60, 110)

    bot_cx, bot_cy = 640, 520
    bot_shadow_points = [
        (bot_cx - 120, bot_cy + 175),
        (bot_cx + 120, bot_cy + 175),
        (bot_cx + 220, bot_cy + 250),
        (bot_cx - 20, bot_cy + 250)
    ]
    fill_polygon(buf, bot_shadow_points, 55, 110, 60, 110)

    # 2. THE PLANT IS A SPROUT, not a grown flower:
    sprout_x, sprout_y = 360, 560
    draw_line(buf, sprout_x, sprout_y, sprout_x + 12, sprout_y - 95, 82, 150, 70, 255)
    draw_line(buf, sprout_x + 1, sprout_y, sprout_x + 13, sprout_y - 95, 82, 150, 70, 255)
    draw_line(buf, sprout_x - 1, sprout_y, sprout_x + 11, sprout_y - 95, 82, 150, 70, 255)

    fill_ellipse(buf, sprout_x - 22, sprout_y - 45, 28, 12, 102, 176, 85, 255)
    fill_ellipse(buf, sprout_x + 32, sprout_y - 55, 26, 12, 102, 176, 85, 255)

    lb_x, lb_y = sprout_x - 28, sprout_y - 46
    fill_ellipse(buf, lb_x, lb_y, 8, 6, 220, 50, 50, 255)
    fill_circle(buf, lb_x - 2, lb_y, 2, 30, 30, 30, 255)
    fill_circle(buf, lb_x + 2, lb_y - 2, 2, 30, 30, 30, 255)

    bud_x, bud_y = sprout_x + 14, sprout_y - 110
    for angle_deg in range(0, 360, 45):
        rad = math.radians(angle_deg)
        px = bud_x + int(14 * math.cos(rad))
        py = bud_y + int(14 * math.sin(rad))
        fill_ellipse(buf, px, py, 10, 6, 255, 220, 60, 255)
    fill_circle(buf, bud_x, bud_y, 12, 125, 75, 40, 255)

    butterflies = [
        (bud_x - 70, bud_y - 50),
        (200, 380),
        (820, 400)
    ]
    for bf_x, bf_y in butterflies:
        fill_ellipse(buf, bf_x - 12, bf_y - 9, 14, 9, 255, 160, 200, 220)
        fill_ellipse(buf, bf_x + 12, bf_y - 9, 14, 9, 255, 160, 200, 220)
        fill_ellipse(buf, bf_x - 10, bf_y + 9, 11, 8, 255, 200, 120, 220)
        fill_ellipse(buf, bf_x + 10, bf_y + 9, 11, 8, 255, 200, 120, 220)
        draw_line(buf, bf_x, bf_y - 14, bf_x, bf_y + 14, 50, 50, 50, 255)

    # 3. FILL THE FRAME & MAKE HERO BIGGER: Robot
    fill_rounded_rect(buf, bot_cx - 130, bot_cy - 10, 260, 200, 45, 245, 242, 235, 255)
    fill_rounded_rect(buf, bot_cx - 85, bot_cy + 20, 170, 100, 22, 210, 230, 235, 255)
    fill_circle(buf, bot_cx, bot_cy + 70, 14, 255, 140, 140, 255)

    head_cy = bot_cy - 125
    fill_circle(buf, bot_cx, head_cy, 110, 245, 242, 235, 255)
    
    draw_line(buf, bot_cx, head_cy - 110, bot_cx, head_cy - 155, 180, 180, 180, 255)
    draw_radial_glow(buf, bot_cx, head_cy - 155, 30, (255, 240, 150), 200)
    fill_circle(buf, bot_cx, head_cy - 155, 12, 255, 220, 80, 255)

    fill_ellipse(buf, bot_cx - 40, head_cy - 12, 26, 32, 50, 60, 75, 255)
    fill_circle(buf, bot_cx - 32, head_cy - 22, 9, 255, 255, 255, 255)
    fill_circle(buf, bot_cx - 46, head_cy + 2, 5, 255, 255, 255, 255)
    
    fill_ellipse(buf, bot_cx + 40, head_cy - 12, 26, 32, 50, 60, 75, 255)
    fill_circle(buf, bot_cx + 48, head_cy - 22, 9, 255, 255, 255, 255)
    fill_circle(buf, bot_cx + 34, head_cy + 2, 5, 255, 255, 255, 255)

    fill_circle(buf, bot_cx - 60, head_cy + 15, 16, 255, 165, 175, 190)
    fill_circle(buf, bot_cx + 60, head_cy + 15, 16, 255, 165, 175, 190)

    for sx_off in range(-20, 21):
        sy_off = int(30 - 0.03 * (sx_off * sx_off))
        buf.set_pixel(bot_cx + sx_off, head_cy + sy_off, 60, 70, 85, 255)
        buf.set_pixel(bot_cx + sx_off, head_cy + sy_off + 1, 60, 70, 85, 255)
        buf.set_pixel(bot_cx + sx_off, head_cy + sy_off + 2, 60, 70, 85, 255)

    # 4. GOLDEN-HOUR WARMTH: warm golden rim light on sun-facing side
    for ry in range(head_cy - 105, head_cy + 105):
        for rx in range(bot_cx - 110, bot_cx - 95):
            dx = rx - bot_cx
            dy = ry - head_cy
            if dx*dx + dy*dy <= 110*110 and dx*dx + dy*dy >= 95*95:
                buf.set_pixel(rx, ry, 255, 225, 130, 220)

    for ry in range(bot_cy - 5, bot_cy + 185):
        for rx in range(bot_cx - 130, bot_cx - 115):
            buf.set_pixel(rx, ry, 255, 225, 130, 220)

    fill_rounded_rect(buf, bot_cx - 180, bot_cy + 30, 50, 25, 12, 225, 222, 215, 255)
    fill_circle(buf, bot_cx - 180, bot_cy + 42, 14, 235, 232, 225, 255)

    fill_rounded_rect(buf, bot_cx + 130, bot_cy + 35, 50, 25, 12, 225, 222, 215, 255)
    fill_circle(buf, bot_cx + 180, bot_cy + 47, 14, 235, 232, 225, 255)

    fill_rounded_rect(buf, bot_cx - 100, bot_cy + 165, 200, 40, 18, 80, 90, 105, 255)
    fill_circle(buf, bot_cx - 65, bot_cy + 185, 14, 50, 55, 65, 255)
    fill_circle(buf, bot_cx + 65, bot_cy + 185, 14, 50, 55, 65, 255)

    # 1. WATERING CAN:
    wc_x, wc_y = bot_cx - 195, bot_cy + 10
    fill_rounded_rect(buf, wc_x - 55, wc_y - 35, 95, 75, 24, 70, 140, 200, 255)
    fill_rounded_rect(buf, wc_x - 12, wc_y - 68, 42, 36, 12, 90, 160, 220, 255)
    
    spout_tip_x, spout_tip_y = bud_x + 10, bud_y + 15
    fill_polygon(buf, [
        (wc_x + 40, wc_y - 10),
        (wc_x + 45, wc_y + 10),
        (spout_tip_x + 6, spout_tip_y - 5),
        (spout_tip_x - 6, spout_tip_y - 12)
    ], 70, 140, 200, 255)
    fill_ellipse(buf, spout_tip_x, spout_tip_y - 8, 8, 14, 90, 160, 220, 255)

    air_droplets = [
        (spout_tip_x - 4, spout_tip_y + 2),
        (spout_tip_x - 10, spout_tip_y + 12),
        (spout_tip_x - 16, spout_tip_y + 22),
        (spout_tip_x - 22, spout_tip_y + 32),
        (spout_tip_x - 28, spout_tip_y + 42),
        (spout_tip_x - 34, spout_tip_y + 52)
    ]
    for dx_p, dy_p in air_droplets:
        fill_circle(buf, dx_p, dy_p, 5, 130, 205, 255, 240)
        fill_circle(buf, dx_p, dy_p, 2, 210, 245, 255, 255)

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
