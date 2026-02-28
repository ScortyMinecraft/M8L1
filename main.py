# -*- coding: utf-8 -*-
"""
Потоп (Flood) — вертикальный скроллер-выживание.
Последний компьютер на крыше небоскреба. Дроны ищут артефакты, вода поднимается.
"""

import pygame
import random
import math
import json
import os

# --- Константы ---
FPS = 60
TITLE = "Потоп (Flood)"

# Артефакты: название, монеты за сбор, замедляет воду (сек)
ARTIFACTS = {
    "solar_panel": ("Солнечная панель", 15, 10),
    "seeds": ("Семена", 8, 0),
    "blueprints": ("Чертежи", 25, 0),
}

def load_config():
    path = os.path.join(os.path.dirname(__file__), "config.json")
    defaults = {
        "screen_width": 1200,
        "screen_height": 700,
        "panel_left_width": 720,
        "water_rise_speed": 18,
        "water_slow_duration": 10,
        "water_slow_factor": 0.3,
        "drone_speed": 4,
        "wind_strength": 2.0,
        "lightning_interval_min": 1.5,
        "lightning_interval_max": 4.0,
        "high_score": 0,
        "coins": 0,
        "drone_speed_bonus": 0,
        "energy_max_bonus": 0,
        "slow_duration_bonus": 0,
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            defaults.update(data)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults

def save_config(data_update):
    path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.update(data_update)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_high_score(score):
    save_config({"high_score": max(load_config().get("high_score", 0), int(score))})


class Water:
    """Уровень воды: поднимается в реальном времени, можно замедлить (солнечная панель)."""
    def __init__(self, config, screen_height):
        self.config = config
        self.screen_height = screen_height
        # В Pygame Y растёт вниз: меньше Y = выше. Вода «поднимается», когда level уменьшается.
        self.level = screen_height * 0.75  # старт внизу экрана, есть запас до крыши
        self.rise_speed = max(10.0, float(config.get("water_rise_speed", 18)))
        self.slow_until = 0
        self.slow_factor = config["water_slow_factor"]

    def update(self, dt_sec):
        if pygame.time.get_ticks() / 1000.0 < self.slow_until:
            speed = self.rise_speed * self.slow_factor
        else:
            speed = self.rise_speed
        # Вода поднимается: уменьшаем Y (пикселей в секунду — заметно)
        self.level -= speed * dt_sec

    def apply_solar_panel(self):
        self.slow_until = pygame.time.get_ticks() / 1000.0 + self.config["water_slow_duration"]

    def draw(self, surface, left_panel_rect, font=None):
        # Вода — градиент от тёмно-синего к поверхности
        water_rect = pygame.Rect(
            left_panel_rect.x,
            int(self.level),
            left_panel_rect.width,
            left_panel_rect.bottom - int(self.level),
        )
        if water_rect.height <= 0:
            return
        color_dark = (25, 50, 95)
        color_surface = (40, 80, 150)
        for i in range(water_rect.height):
            t = i / max(water_rect.height, 1)
            r = int(color_dark[0] + (color_surface[0] - color_dark[0]) * t)
            g = int(color_dark[1] + (color_surface[1] - color_dark[1]) * t)
            b = int(color_dark[2] + (color_surface[2] - color_dark[2]) * t)
            pygame.draw.line(
                surface,
                (r, g, b),
                (water_rect.x, water_rect.bottom - i),
                (water_rect.right, water_rect.bottom - i),
            )
        # Линия горизонта воды — слегка волнистая, чтобы видно было подъём
        y_line = water_rect.top
        t = pygame.time.get_ticks() / 200.0
        pts = []
        for px in range(water_rect.x, water_rect.right + 1, 12):
            wave = 2 * math.sin(px * 0.02 + t) + 1.5 * math.sin(px * 0.01 + t * 1.3)
            pts.append((px, int(y_line + wave)))
        if len(pts) >= 2:
            pygame.draw.lines(surface, (180, 210, 255), False, pts, 2)
            pygame.draw.lines(surface, (100, 150, 220), False, pts, 1)
        if font:
            label = font.render("УРОВЕНЬ ВОДЫ ↑ поднимается", True, (220, 240, 255))
            surface.blit(label, (water_rect.x + 12, y_line - 22))

    def is_game_over(self, roof_y):
        return self.level <= roof_y  # вода дошла до крыши (уровень поднялся)


class Building:
    """Крыша соседнего здания — цель для дрона, может содержать артефакт."""
    def __init__(self, x, y, width, height, has_artifact="solar_panel"):
        self.rect = pygame.Rect(x, y, width, height)
        self.has_artifact = has_artifact
        self.collected = False

    def draw(self, surface, water_level, font=None):
        # Не рисуем, если здание полностью под водой (Y растёт вниз: вода выше = меньше Y)
        if self.rect.top >= water_level:
            return
        visible_bottom = min(self.rect.bottom, water_level)
        visible_rect = pygame.Rect(
            self.rect.x, self.rect.top,
            self.rect.width, visible_bottom - self.rect.top,
        )
        if visible_rect.height <= 0:
            return
        # Корпус здания под крышей (стена над водой)
        body = pygame.Rect(self.rect.x, visible_rect.bottom, self.rect.width, 80)
        if body.top < water_level:
            clip = min(body.bottom, water_level) - body.top
            if clip > 0:
                pygame.draw.rect(surface, (50, 55, 65), (body.x, body.top, body.width, clip))
        # Крыша — яркая платформа
        pygame.draw.rect(surface, (90, 95, 105), visible_rect)
        pygame.draw.rect(surface, (140, 145, 155), visible_rect, 3)
        if self.has_artifact and not self.collected:
            cx = self.rect.centerx
            cy = visible_rect.centery
            name = ARTIFACTS.get(self.has_artifact, ("?", 0, 0))[0]
            colors = {"solar_panel": (220, 180, 40), "seeds": (80, 160, 80), "blueprints": (100, 140, 200)}
            c = colors.get(self.has_artifact, (200, 200, 200))
            pygame.draw.rect(surface, c, (cx - 14, cy - 14, 28, 28))
            pygame.draw.rect(surface, (255, 255, 255), (cx - 14, cy - 14, 28, 28), 2)
            if font:
                art = font.render(name, True, (255, 255, 255))
                surface.blit(art, (cx - art.get_width() // 2, cy - 32))


class Drone:
    """Дрон: управление WASD/стрелками, сносится ветром, урон от молний. При касании крыши — сбор артефакта."""
    def __init__(self, config, start_pos, speed_bonus=0):
        self.config = config
        self.pos = list(start_pos)
        self.speed = (config["drone_speed"] + speed_bonus) * 60 * 0.016  # пикселей за кадр
        self.wind = [0.0, 0.0]
        self.health = 100
        self.radius = 18

    def update(self, dt_sec, keys, left_panel_rect):
        # Управление: WASD или стрелки
        dx = dy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += 1
        if dx or dy:
            norm = math.hypot(dx, dy)
            self.pos[0] += (dx / norm) * self.speed
            self.pos[1] += (dy / norm) * self.speed
        # Ветер сносит
        self.wind[0] += (random.uniform(-1, 1) * self.config["wind_strength"] - self.wind[0] * 0.05) * dt_sec * 25
        self.wind[1] += (random.uniform(-1, 1) * self.config["wind_strength"] - self.wind[1] * 0.05) * dt_sec * 25
        self.pos[0] += self.wind[0] * dt_sec * 20
        self.pos[1] += self.wind[1] * dt_sec * 20
        # Границы левой панели
        self.pos[0] = max(left_panel_rect.x + self.radius, min(left_panel_rect.right - self.radius, self.pos[0]))
        self.pos[1] = max(left_panel_rect.y + self.radius, min(left_panel_rect.bottom - self.radius, self.pos[1]))

    def get_rect(self):
        return pygame.Rect(self.pos[0] - self.radius, self.pos[1] - self.radius, self.radius * 2, self.radius * 2)

    def take_lightning_damage(self, amount=35):
        self.health -= amount

    def draw(self, surface, font=None):
        x, y = int(self.pos[0]), int(self.pos[1])
        r = self.radius
        # Корпус дрона — горизонтальный «тело» (овал)
        body_rect = pygame.Rect(x - r - 4, y - r // 2, r * 2 + 8, r)
        pygame.draw.ellipse(surface, (220, 225, 235), body_rect)
        pygame.draw.ellipse(surface, (100, 105, 115), body_rect, 2)
        # Четыре «луча» к пропеллерам
        for angle in [0, math.pi / 2, math.pi, 3 * math.pi / 2]:
            ax = x + (r + 6) * math.cos(angle)
            ay = y + (r + 6) * math.sin(angle)
            pygame.draw.line(surface, (120, 125, 135), (x, y), (ax, ay), 3)
            pygame.draw.circle(surface, (180, 185, 195), (int(ax), int(ay)), 6)
            pygame.draw.circle(surface, (90, 95, 100), (int(ax), int(ay)), 6, 1)
        # Подпись «Дрон»
        if font:
            lbl = font.render("Дрон", True, (255, 255, 255))
            surface.blit(lbl, (x - lbl.get_width() // 2, y - r - 22))


class Lightning:
    """Молния: вспышка в случайной позиции, наносит урон дрону при пересечении."""
    def __init__(self, left_panel_rect):
        self.rect = pygame.Rect(
            left_panel_rect.x + random.randint(50, left_panel_rect.width - 50),
            left_panel_rect.y + random.randint(50, left_panel_rect.height - 50),
            8,
            random.randint(80, 180),
        )
        self.active_until = pygame.time.get_ticks() + 150
        self.damage_applied = False

    def update(self, drone):
        if not self.damage_applied and drone:
            dr = drone.radius + 15
            if abs(drone.pos[0] - self.rect.centerx) < dr and abs(drone.pos[1] - self.rect.centery) < self.rect.h // 2 + dr:
                drone.take_lightning_damage()
                self.damage_applied = True

    def is_done(self):
        return pygame.time.get_ticks() > self.active_until

    def draw(self, surface):
        if pygame.time.get_ticks() < self.active_until:
            pygame.draw.rect(surface, (200, 220, 255), self.rect)
            pygame.draw.rect(surface, (255, 255, 255), self.rect.inflate(4, 0))


class Button:
    """Простая кнопка, отрисованная через Pygame."""
    def __init__(self, x, y, w, h, text, font):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.font = font
        self.hover = False

    def update_hover(self, pos):
        self.hover = self.rect.collidepoint(pos)

    def draw(self, surface):
        color = (70, 100, 140) if self.hover else (50, 75, 110)
        pygame.draw.rect(surface, color, self.rect)
        pygame.draw.rect(surface, (100, 140, 180), self.rect, 2)
        text_surf = self.font.render(self.text, True, (220, 230, 240))
        tr = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, tr)

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)


def generate_buildings(left_panel_rect, height, count=14):
    """Генерирует здания с разными артефактами (солнечные панели, семена, чертежи)."""
    types = ["solar_panel", "seeds", "blueprints"]
    buildings = []
    for i in range(count):
        x = left_panel_rect.x + 40 + (i % 5) * (left_panel_rect.width // 5) + random.randint(-20, 30)
        y = height * (0.2 + (i // 5) * 0.18) + random.randint(-30, 40)
        w = 70 + random.randint(0, 50)
        h = 40 + random.randint(0, 25)
        art = types[i % 3] if i < 12 else types[random.randint(0, 2)]
        buildings.append(Building(x, y, w, h, art))
    return buildings


def run_game():
    pygame.init()
    config = load_config()
    width = config["screen_width"]
    height = config["screen_height"]
    panel_left_w = config["panel_left_width"]
    screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
    pygame.display.set_caption(TITLE)
    left_panel = pygame.Rect(0, 0, panel_left_w, height)
    right_panel = pygame.Rect(panel_left_w, 0, width - panel_left_w, height)
    font_large = pygame.font.SysFont("Arial", 28)
    font_medium = pygame.font.SysFont("Arial", 20)
    font_small = pygame.font.SysFont("Arial", 16)
    panel_margin = 20
    clock = pygame.time.Clock()

    # Состояния: "menu", "shop", "playing", "game_over", "level_complete"
    state = "menu"
    coins = config.get("coins", 0)
    energy_max = 100 + config.get("energy_max_bonus", 0) * 20
    slow_duration_extra = config.get("slow_duration_bonus", 0) * 5

    # Меню: кнопки
    btn_play = Button(0, 0, 220, 50, "Играть", font_large)
    btn_shop = Button(0, 0, 220, 50, "Магазин", font_large)
    btn_exit = Button(0, 0, 220, 50, "Выход", font_medium)
    btn_back = Button(0, 0, 180, 44, "Назад", font_medium)
    btn_menu_from_end = Button(0, 0, 200, 48, "В меню", font_medium)
    btn_recall = Button(0, 0, 200, 44, "Вернуться на базу", font_small)

    while True:
        dt = clock.tick(FPS) / 1000.0
        mouse_pos = pygame.mouse.get_pos()
        keys = pygame.key.get_pressed()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.VIDEORESIZE:
                width, height = event.w, event.h
                screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
                left_panel = pygame.Rect(0, 0, panel_left_w, height)
                right_panel = pygame.Rect(panel_left_w, 0, width - panel_left_w, height)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "menu":
                    cx, cy = width // 2, height // 2
                    if btn_play.is_clicked(mouse_pos):
                        state = "playing"
                        cfg = load_config()
                        energy_max = 100 + cfg.get("energy_max_bonus", 0) * 20
                        play_config = dict(cfg)
                        play_config["water_slow_duration"] = cfg.get("water_slow_duration", 10) + slow_duration_extra
                        config = play_config
                        water = Water(config, height)
                        water.screen_height = height
                        player_roof_y = height * 0.15
                        buildings = generate_buildings(left_panel, height)
                        drone = None
                        lightnings = []
                        next_lightning = pygame.time.get_ticks() + 2000
                        energy = energy_max
                        survival_start = pygame.time.get_ticks()
                        high_score = cfg.get("high_score", 0)
                        level_coins_earned = 0
                        btn_send = Button(right_panel.x + panel_margin, right_panel.y + 200, 320, 52, "Отправить дрона", font_medium)
                    elif btn_shop.is_clicked(mouse_pos):
                        state = "shop"
                    elif btn_exit.is_clicked(mouse_pos):
                        pygame.quit()
                        return
                elif state == "shop":
                    if btn_back.is_clicked(mouse_pos):
                        state = "menu"
                    else:
                        cfg = load_config()
                        coins = cfg.get("coins", 0)
                        by = 130
                        for name, key, price, current, max_buy in [
                            ("Скорость дрона +1", "drone_speed_bonus", 50, cfg.get("drone_speed_bonus", 0), 3),
                            ("Макс. энергия +20", "energy_max_bonus", 40, cfg.get("energy_max_bonus", 0), 5),
                            ("Замедление воды +5 сек", "slow_duration_bonus", 60, cfg.get("slow_duration_bonus", 0), 3),
                        ]:
                            buy_rect = pygame.Rect(width // 2 + 120, by - 4, 80, 28)
                            if current < max_buy and coins >= price and buy_rect.collidepoint(mouse_pos):
                                save_config({"coins": coins - price, key: current + 1})
                                break
                            by += 42
                elif state == "level_complete":
                    if btn_menu_from_end.is_clicked(mouse_pos):
                        state = "menu"
                        config = load_config()
                        coins = config.get("coins", 0)
                elif state == "game_over":
                    if btn_menu_from_end.is_clicked(mouse_pos):
                        state = "menu"
                elif state == "playing":
                    if drone is None and btn_send.is_clicked(mouse_pos) and energy >= 15:
                        start = (left_panel.centerx, int(player_roof_y - 35))
                        drone = Drone(config, start, config.get("drone_speed_bonus", 0))
                        energy -= 15
                    elif drone and btn_recall.is_clicked(mouse_pos):
                        drone = None

        # ---------- Отрисовка меню ----------
        if state == "menu":
            coins = load_config().get("coins", 0)
            screen.fill((35, 45, 65))
            title = font_large.render("Потоп (Flood)", True, (220, 230, 250))
            screen.blit(title, (width // 2 - title.get_width() // 2, height // 4 - 30))
            sub = font_small.render("Собирайте артефакты. Управляйте дроном — WASD или стрелки.", True, (180, 190, 210))
            screen.blit(sub, (width // 2 - sub.get_width() // 2, height // 4 + 20))
            cx, cy = width // 2, height // 2
            btn_play.rect = pygame.Rect(cx - 110, cy - 80, 220, 50)
            btn_shop.rect = pygame.Rect(cx - 110, cy - 20, 220, 50)
            btn_exit.rect = pygame.Rect(cx - 110, cy + 40, 220, 50)
            btn_play.update_hover(mouse_pos)
            btn_shop.update_hover(mouse_pos)
            btn_exit.update_hover(mouse_pos)
            btn_play.draw(screen)
            btn_shop.draw(screen)
            btn_exit.draw(screen)
            coins_text = font_small.render(f"Монеты: {coins}", True, (255, 220, 100))
            screen.blit(coins_text, (width - coins_text.get_width() - 20, 15))
            pygame.display.flip()
            continue

        # ---------- Магазин ----------
        if state == "shop":
            config = load_config()
            coins = config.get("coins", 0)
            screen.fill((35, 45, 65))
            screen.blit(font_large.render("Магазин", True, (220, 230, 240)), (width // 2 - 50, 30))
            screen.blit(font_medium.render(f"Монеты: {coins}", True, (255, 220, 100)), (width // 2 - 60, 75))
            by = 130
            shop_items = [
                ("Скорость дрона +1", "drone_speed_bonus", 50, config.get("drone_speed_bonus", 0), 3),
                ("Макс. энергия +20", "energy_max_bonus", 40, config.get("energy_max_bonus", 0), 5),
                ("Замедление воды +5 сек", "slow_duration_bonus", 60, config.get("slow_duration_bonus", 0), 3),
            ]
            for name, key, price, current, max_buy in shop_items:
                color = (200, 200, 200) if current < max_buy and coins >= price else (120, 120, 120)
                screen.blit(font_small.render(f"{name} — {price} монет ({current}/{max_buy})", True, color), (width // 2 - 180, by))
                buy_rect = pygame.Rect(width // 2 + 120, by - 4, 80, 28)
                if current < max_buy and coins >= price and buy_rect.collidepoint(mouse_pos):
                    pygame.draw.rect(screen, (80, 140, 80), buy_rect)
                else:
                    pygame.draw.rect(screen, (60, 70, 90), buy_rect)
                screen.blit(font_small.render("Купить", True, (220, 220, 220)), (buy_rect.x + 18, buy_rect.y + 6))
                by += 42
            btn_back.rect = pygame.Rect(width // 2 - 90, height - 80, 180, 44)
            btn_back.update_hover(mouse_pos)
            btn_back.draw(screen)
            pygame.display.flip()
            continue

        if state == "playing":
            if water.screen_height != height:
                water.screen_height = height
                player_roof_y = height * 0.15
            water.update(dt)
            if water.is_game_over(player_roof_y):
                state = "game_over"
                save_high_score((pygame.time.get_ticks() - survival_start) / 1000.0)
                high_score = max(high_score, (pygame.time.get_ticks() - survival_start) / 1000.0)
                continue

            if drone:
                drone.update(dt, keys, left_panel)
                for b in buildings:
                    if not b.collected and b.rect.top < water.level and drone.get_rect().colliderect(b.rect):
                        b.collected = True
                        name, coin_reward, slow_sec = ARTIFACTS.get(b.has_artifact, ("?", 0, 0))
                        level_coins_earned += coin_reward
                        if slow_sec > 0:
                            water.apply_solar_panel()
                        energy = min(energy_max, energy + 15)
                if drone.health <= 0:
                    drone = None
                else:
                    if pygame.time.get_ticks() >= next_lightning:
                        lightnings.append(Lightning(left_panel))
                        next_lightning = pygame.time.get_ticks() + random.randint(1500, 4000)
                    for L in lightnings[:]:
                        L.update(drone)
                        if L.is_done():
                            lightnings.remove(L)

            all_collected = all(b.collected for b in buildings)
            if all_collected:
                state = "level_complete"
                save_config({"coins": load_config().get("coins", 0) + level_coins_earned})
                continue

        if state == "game_over":
            screen.fill((30, 30, 40))
            screen.blit(font_large.render("Вода достигла крыши. Игра окончена.", True, (220, 100, 100)), (width // 2 - 220, height // 2 - 60))
            screen.blit(font_medium.render(f"Время: {(pygame.time.get_ticks()-survival_start)/1000:.1f} с. Рекорд: {high_score:.1f} с.", True, (200, 200, 200)), (width // 2 - 150, height // 2 - 15))
            btn_menu_from_end.rect = pygame.Rect(width // 2 - 100, height // 2 + 30, 200, 48)
            btn_menu_from_end.update_hover(mouse_pos)
            btn_menu_from_end.draw(screen)
            pygame.display.flip()
            continue

        if state == "level_complete":
            screen.fill((30, 50, 40))
            screen.blit(font_large.render("Уровень пройден!", True, (120, 255, 150)), (width // 2 - 120, height // 2 - 80))
            screen.blit(font_medium.render("Все артефакты собраны. Миссия выполнена.", True, (200, 220, 200)), (width // 2 - 180, height // 2 - 40))
            screen.blit(font_medium.render(f"+{level_coins_earned} монет", True, (255, 220, 100)), (width // 2 - 60, height // 2))
            btn_menu_from_end.rect = pygame.Rect(width // 2 - 100, height // 2 + 50, 200, 48)
            btn_menu_from_end.update_hover(mouse_pos)
            btn_menu_from_end.draw(screen)
            pygame.display.flip()
            continue

        btn_send.update_hover(mouse_pos)

        # Отрисовка
        # Левая панель — небо и вода
        screen.fill((50, 60, 85), left_panel)  # небо
        water.draw(screen, left_panel, font_small)
        # Крыша игрока — явная платформа и подпись
        roof_h = 28
        roof_rect = pygame.Rect(left_panel.x, int(player_roof_y) - roof_h, left_panel.width, roof_h)
        pygame.draw.rect(screen, (120, 125, 135), roof_rect)
        pygame.draw.rect(screen, (180, 185, 195), roof_rect, 3)
        roof_label = font_medium.render("ВАША КРЫША — сюда не должна дойти вода!", True, (255, 255, 255))
        screen.blit(roof_label, (left_panel.x + 20, int(player_roof_y) - roof_h - 26))
        pygame.draw.rect(screen, (70, 75, 90), (left_panel.x, 0, left_panel.width, roof_rect.top))
        for b in buildings:
            b.draw(screen, water.level, font_small)
        for L in lightnings:
            L.draw(screen)
        if drone:
            drone.draw(screen, font_small)

        # Правая панель — UI (чёткая сетка, без наложений)
        screen.fill((38, 48, 65), right_panel)
        px = right_panel.x + panel_margin
        py = right_panel.y
        survival_sec = (pygame.time.get_ticks() - survival_start) / 1000.0
        high_score = max(high_score, survival_sec)

        screen.blit(font_large.render("Потоп", True, (220, 230, 240)), (px, py + 10))
        screen.blit(font_small.render(f"Время: {survival_sec:.1f} с  |  Рекорд: {high_score:.1f} с", True, (190, 200, 210)), (px, py + 42))
        py += 72

        # Блок «До крыши»: подпись + столбик + статус в одну строку
        screen.blit(font_small.render("До крыши:", True, (200, 210, 220)), (px, py))
        bar_x, bar_y = px + 90, py - 2
        bar_w, bar_h = 24, 56
        total_range = max((height * 0.75 - player_roof_y), 1)
        remaining = max(0, min(1, (water.level - player_roof_y) / total_range))
        pygame.draw.rect(screen, (45, 48, 58), (bar_x, bar_y, bar_w, bar_h))
        fill_h = int(bar_h * remaining)
        if fill_h > 0:
            pygame.draw.rect(screen, (70, 120, 200), (bar_x + 2, bar_y + bar_h - fill_h, bar_w - 4, fill_h))
        pygame.draw.rect(screen, (90, 95, 110), (bar_x, bar_y, bar_w, bar_h), 2)
        status = "Опасно!" if remaining < 0.25 else "Есть запас"
        status_color = (255, 120, 100) if remaining < 0.25 else (140, 200, 255)
        screen.blit(font_small.render(status, True, status_color), (bar_x + bar_w + 10, bar_y + bar_h // 2 - 8))
        py += 68

        # Кнопка отправки дрона / Вернуться на базу
        btn_send.rect.x = px
        btn_send.rect.y = py
        btn_send.rect.width = min(320, right_panel.width - panel_margin * 2)
        if drone is None:
            btn_send.draw(screen)
            if energy < 15:
                screen.blit(font_small.render("Нужно 15 энергии", True, (200, 120, 100)), (px, py + 56))
        else:
            btn_recall.rect = pygame.Rect(px, py, min(220, right_panel.width - panel_margin * 2), 44)
            btn_recall.update_hover(mouse_pos)
            btn_recall.draw(screen)
            screen.blit(font_small.render("WASD — управление дроном", True, (180, 200, 220)), (px, py + 48))
        py += 80

        # Энергия
        screen.blit(font_small.render("Энергия:", True, (200, 210, 220)), (px, py))
        ebar_y = py + 20
        ebar_w = min(220, right_panel.width - panel_margin * 2 - 80)
        pygame.draw.rect(screen, (45, 48, 58), (px, ebar_y, ebar_w, 22))
        pygame.draw.rect(screen, (60, 130, 200), (px + 2, ebar_y + 2, max(0, int(ebar_w * energy / max(energy_max, 1)) - 4), 18))
        screen.blit(font_small.render(f"{int(energy)}/{energy_max}", True, (180, 190, 200)), (px + ebar_w + 8, ebar_y - 2))
        py += 52

        # Подсказка и монеты
        screen.blit(font_small.render("WASD/стрелки — летать. Коснитесь крыши — собрать артефакт.", True, (170, 180, 190)), (px, py))
        screen.blit(font_small.render(f"Монет за уровень: +{level_coins_earned}", True, (255, 220, 120)), (px, py + 20))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    run_game()
