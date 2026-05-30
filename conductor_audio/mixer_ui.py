"""Pygame mixer UI for the audio engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

from .auto_detect import SECTION_ORDER

_VOLUME_STEP = 0.10

_ASSETS_DIR = Path(__file__).parent


WINDOW_SIZE = (1200, 700)
FPS = 60
BG = (30, 30, 30)
PANEL = (42, 42, 48)
PANEL_DIM = (28, 28, 32)
TEXT = (238, 238, 242)
MUTED_TEXT = (130, 130, 140)
SUBTLE = (88, 88, 96)
ACCENT = (168, 85, 247)
GREEN = (34, 197, 94)
RED = (239, 68, 68)
YELLOW = (234, 179, 8)
CYAN = (70, 210, 255)

SECTION_LABELS = {
    "strings": "Strings",
    "vocals": "Vocals",
    "rhythm": "Rhythm",
    "atmosphere": "Atmosphere",
}

TEMPO_STEPS = (100, 120, 140, 160, 180)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def section_target_number(section: str) -> int:
    return SECTION_ORDER.index(section) + 1


def nearest_tempo_step(bpm: float) -> int:
    return min(TEMPO_STEPS, key=lambda step: abs(step - bpm))


def next_tempo_step(bpm: float) -> int:
    current = nearest_tempo_step(bpm)
    index = TEMPO_STEPS.index(current)
    return TEMPO_STEPS[min(index + 1, len(TEMPO_STEPS) - 1)]


def previous_tempo_step(bpm: float) -> int:
    current = nearest_tempo_step(bpm)
    index = TEMPO_STEPS.index(current)
    return TEMPO_STEPS[max(index - 1, 0)]


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    active: bool = False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, dimmed: bool = False) -> None:
        color = ACCENT if self.active else (58, 58, 66)
        if dimmed:
            color = tuple(max(0, c - 24) for c in color)
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, (92, 92, 102), self.rect, 1, border_radius=6)
        label_surface = font.render(self.label, True, TEXT if not dimmed else MUTED_TEXT)
        screen.blit(label_surface, label_surface.get_rect(center=self.rect.center))

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


class MixerUI:
    def __init__(self, engine, hand_tracker=None) -> None:
        pygame.init()
        self.engine = engine
        self.hand_tracker = hand_tracker
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.SCALED)
        pygame.display.set_caption("Conductor Baton Mixer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 20)
        self.small_font = pygame.font.SysFont("Arial", 14)
        self.title_font = pygame.font.SysFont("Arial", 28, bold=True)
        self.bpm_font = pygame.font.SysFont("Arial", 36, bold=True)
        raw_bg = pygame.image.load(_ASSETS_DIR / "orchestra.png").convert()
        self.bg = pygame.transform.scale(raw_bg, WINDOW_SIZE)
        self.running = True
        self.dragging: tuple[str, str] | None = None
        self.command_mode: str | None = None
        self._tempo_gesture_armed = True
        self.base_volumes = {section: 1.0 for section in SECTION_ORDER}
        self.muted = {section: False for section in SECTION_ORDER}
        self.soloed = {section: False for section in SECTION_ORDER}
        self.original_tempo = self.engine.get_state()["original_tempo"]
        self.tempo = nearest_tempo_step(self.original_tempo)
        self.engine.set_tempo(self.tempo)
        self.layout = self._build_layout()
        _section_filenames = {
            "strings": "strings.png",
            "vocals": "vocal.png",
            "rhythm": "rhythm.png",
            "atmosphere": "atmosphere.png",
        }
        self.section_images: dict[str, pygame.Surface] = {}
        for section, filename in _section_filenames.items():
            raw = pygame.image.load(_ASSETS_DIR / filename).convert()
            self.section_images[section] = pygame.transform.scale(raw, (64, 64))

    def run(self) -> None:
        while self.running:
            self._handle_events()
            self._draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()

    def draw_once(self) -> None:
        self._draw()
        pygame.display.flip()

    def _build_layout(self) -> dict[str, dict[str, pygame.Rect]]:
        layout: dict[str, dict[str, pygame.Rect]] = {}
        margin = 24
        gap = 16
        tempo_width = 160
        strip_width = (WINDOW_SIZE[0] - margin * 2 - tempo_width - gap * 4) // 4
        x = margin
        for section in SECTION_ORDER:
            strip = pygame.Rect(x, 24, strip_width, 652)
            layout[section] = {
                "strip": strip,
                "fader": pygame.Rect(strip.centerx - 24, 132, 48, 420),
                "meter": pygame.Rect(strip.centerx + 42, 132, 14, 420),
                "mute": pygame.Rect(strip.x + 30, 610, 48, 34),
                "solo": pygame.Rect(strip.right - 78, 610, 48, 34),
            }
            x += strip_width + gap
        layout["tempo"] = {
            "strip": pygame.Rect(x, 24, tempo_width, 652),
            "steps": pygame.Rect(x + 22, 196, tempo_width - 44, 292),
        }
        return layout

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.dragging = None
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self._handle_drag(event.pos, event.rel)

    def _handle_key(self, event: pygame.event.Event) -> None:
        key = event.key
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
        elif key == pygame.K_SPACE:
            self.engine.toggle_pause()
        elif key in (pygame.K_m, pygame.K_s):
            self.command_mode = "mute" if key == pygame.K_m else "solo"
        elif key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self._set_tempo(next_tempo_step(self.tempo))
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self._set_tempo(previous_tempo_step(self.tempo))
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            section = SECTION_ORDER[[pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4].index(key)]
            if self.command_mode == "mute":
                self.muted[section] = not self.muted[section]
                self.command_mode = None
                self._apply_effective_volumes()
            elif self.command_mode == "solo":
                self.soloed[section] = not self.soloed[section]
                self.command_mode = None
                self._apply_effective_volumes()
            else:
                step = -_VOLUME_STEP if (event.mod & pygame.KMOD_SHIFT) else _VOLUME_STEP
                self._set_base_volume(section, self.base_volumes[section] + step)

    def _handle_mouse_down(self, pos: tuple[int, int]) -> None:
        tempo = self.layout["tempo"]
        for bpm, rect in self._tempo_step_rects():
            if rect.collidepoint(pos):
                self._set_tempo(bpm)
                return
        for section in SECTION_ORDER:
            strip = self.layout[section]
            if strip["fader"].inflate(28, 8).collidepoint(pos):
                self.dragging = (section, "fader")
                self._set_volume_from_pos(section, pos[1])
            elif strip["mute"].collidepoint(pos):
                self.muted[section] = not self.muted[section]
                self._apply_effective_volumes()
            elif strip["solo"].collidepoint(pos):
                self.soloed[section] = not self.soloed[section]
                self._apply_effective_volumes()

    def _handle_drag(self, pos: tuple[int, int], rel: tuple[int, int]) -> None:
        target, control = self.dragging
        if control == "fader":
            self._set_volume_from_pos(target, pos[1])

    def _set_base_volume(self, section: str, value: float) -> None:
        self.base_volumes[section] = clamp(value, 0.0, 1.0)
        self._apply_effective_volumes()

    def _set_volume_from_pos(self, section: str, y: int) -> None:
        rect = self.layout[section]["fader"]
        value = 1.0 - (y - rect.top) / rect.height
        self._set_base_volume(section, value)

    def _set_tempo(self, bpm: float) -> None:
        self.tempo = nearest_tempo_step(bpm)
        self.engine.set_tempo(self.tempo)

    def _tempo_step_rects(self) -> list[tuple[int, pygame.Rect]]:
        rect = self.layout["tempo"]["steps"]
        gap = 10
        button_height = (rect.height - gap * (len(TEMPO_STEPS) - 1)) // len(TEMPO_STEPS)
        buttons = []
        for index, bpm in enumerate(reversed(TEMPO_STEPS)):
            y = rect.y + index * (button_height + gap)
            buttons.append((bpm, pygame.Rect(rect.x, y, rect.width, button_height)))
        return buttons

    def _apply_effective_volumes(self) -> None:
        any_solo = any(self.soloed.values())
        for section in SECTION_ORDER:
            audible = not self.muted[section] and (not any_solo or self.soloed[section])
            self.engine.set_volume(section, self.base_volumes[section] if audible else 0.0)

    def _draw_panel(self, rect: pygame.Rect, color: tuple, alpha: int, border_radius: int = 8) -> None:
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (*color, alpha), surf.get_rect(), border_radius=border_radius)
        self.screen.blit(surf, rect.topleft)

    def _draw(self) -> None:
        state = self.engine.get_state()
        hand_state = self._hand_state()
        self._apply_hand_tempo_gesture(hand_state)
        self.screen.blit(self.bg, (0, 0))
        for section in SECTION_ORDER:
            self._draw_section(section, state, hand_state)
        self._draw_tempo(state, hand_state)
        if self.command_mode:
            msg = f"{self.command_mode.upper()} target: press 1-4"
            surface = self.font.render(msg, True, YELLOW)
            self.screen.blit(surface, (24, WINDOW_SIZE[1] - 28))

    def _draw_section(self, section: str, state: dict, hand_state=None) -> None:
        strip = self.layout[section]
        any_solo = any(self.soloed.values())
        dimmed = self.muted[section] or (any_solo and not self.soloed[section])
        hand_target = self._hand_targeted_section(hand_state)
        hand_active = hand_target == section or hand_target == "all"
        self._draw_panel(strip["strip"], PANEL_DIM if dimmed else PANEL, 180)
        border_color = CYAN if hand_active else (66, 66, 76)
        border_width = 4 if hand_active else 1
        pygame.draw.rect(self.screen, border_color, strip["strip"], border_width, border_radius=8)

        label = SECTION_LABELS[section]
        label_color = CYAN if hand_active else TEXT if not dimmed else MUTED_TEXT
        label_surface = self.title_font.render(label, True, label_color)
        self.screen.blit(label_surface, label_surface.get_rect(center=(strip["strip"].centerx, strip["strip"].y + 72)))
        self._draw_section_number(section, strip["strip"], hand_active, dimmed)

        self._draw_fader(strip["fader"], self.base_volumes[section], dimmed)
        self._draw_meter(strip["meter"], state["meters"].get(section, 0.0), dimmed)

        Button(strip["mute"], "M", self.muted[section]).draw(self.screen, self.small_font, dimmed)
        Button(strip["solo"], "S", self.soloed[section]).draw(self.screen, self.small_font, dimmed)
        icon = self.section_images[section]
        icon_rect = icon.get_rect(center=(strip["strip"].centerx, strip["mute"].centery))
        self.screen.blit(icon, icon_rect)
        pygame.draw.rect(self.screen, SUBTLE, icon_rect, 2, border_radius=10)

    def _draw_section_number(self, section: str, rect: pygame.Rect, active: bool, dimmed: bool) -> None:
        badge = pygame.Rect(0, 0, 42, 42)
        badge.center = (rect.centerx, rect.y + 34)
        fill = CYAN if active else (58, 58, 66)
        if dimmed and not active:
            fill = PANEL_DIM
        pygame.draw.rect(self.screen, fill, badge, border_radius=21)
        pygame.draw.rect(self.screen, (112, 112, 122), badge, 1, border_radius=21)
        color = (18, 22, 24) if active else TEXT if not dimmed else MUTED_TEXT
        surface = self.title_font.render(str(section_target_number(section)), True, color)
        self.screen.blit(surface, surface.get_rect(center=badge.center))

    def _draw_fader(self, rect: pygame.Rect, value: float, dimmed: bool) -> None:
        pygame.draw.rect(self.screen, (22, 22, 26), rect, border_radius=8)
        fill = pygame.Rect(rect.x, rect.y + int((1 - value) * rect.height), rect.width, int(value * rect.height))
        pygame.draw.rect(self.screen, ACCENT if not dimmed else SUBTLE, fill, border_radius=8)
        handle_y = rect.bottom - int(value * rect.height)
        handle = pygame.Rect(rect.x - 10, handle_y - 6, rect.width + 20, 12)
        pygame.draw.rect(self.screen, TEXT if not dimmed else MUTED_TEXT, handle, border_radius=6)
        top = self.small_font.render("0", True, SUBTLE)
        bottom = self.small_font.render("-∞", True, SUBTLE)
        self.screen.blit(top, (rect.x - 34, rect.top - 4))
        self.screen.blit(bottom, (rect.x - 36, rect.bottom - 12))

    def _draw_meter(self, rect: pygame.Rect, value: float, dimmed: bool) -> None:
        pygame.draw.rect(self.screen, (18, 18, 22), rect, border_radius=4)
        fill_height = int(rect.height * value)
        color = GREEN if value < 0.75 else YELLOW
        if dimmed:
            color = SUBTLE
        pygame.draw.rect(
            self.screen,
            color,
            pygame.Rect(rect.x, rect.bottom - fill_height, rect.width, fill_height),
            border_radius=4,
        )

    def _draw_tempo(self, state: dict, hand_state=None) -> None:
        strip = self.layout["tempo"]
        self._draw_panel(strip["strip"], PANEL, 180)
        pygame.draw.rect(self.screen, (66, 66, 76), strip["strip"], 1, border_radius=8)
        label = self.title_font.render("Tempo", True, TEXT)
        self.screen.blit(label, label.get_rect(center=(strip["strip"].centerx, 64)))
        bpm_surface = self.bpm_font.render(f"{round(self.tempo):03d} BPM", True, TEXT)
        self.screen.blit(bpm_surface, bpm_surface.get_rect(center=(strip["strip"].centerx, 126)))

        self._draw_tempo_steps()
        self._draw_hand_status(strip["strip"], hand_state)
        if state.get("paused"):
            paused = self.font.render("Paused", True, RED)
            self.screen.blit(paused, paused.get_rect(center=(strip["strip"].centerx, 646)))

    def _draw_tempo_steps(self) -> None:
        for bpm, rect in self._tempo_step_rects():
            Button(rect, str(bpm), self.tempo == bpm).draw(self.screen, self.font)

    def _draw_hand_status(self, rect: pygame.Rect, hand_state) -> None:
        y = 522
        title = self.small_font.render("Hand Tracking", True, MUTED_TEXT)
        self.screen.blit(title, title.get_rect(center=(rect.centerx, y)))
        if hand_state is None:
            lines = ("off", "", "")
        else:
            detected = "yes" if hand_state.detected else "no"
            target = hand_state.targeted_section or "none"
            gesture = hand_state.tempo_gesture or "none"
            lines = (
                f"detected {detected}",
                f"{hand_state.fingers_extended} fingers",
                f"target {target}",
                f"tempo {gesture}",
            )
        for index, line in enumerate(lines):
            surface = self.small_font.render(line, True, TEXT if hand_state is not None else MUTED_TEXT)
            self.screen.blit(surface, surface.get_rect(center=(rect.centerx, y + 24 + index * 20)))

    def _hand_state(self):
        if self.hand_tracker is None:
            return None
        return self.hand_tracker.get_state()

    def _apply_hand_tempo_gesture(self, hand_state) -> None:
        gesture = None
        if hand_state is not None and hand_state.detected:
            gesture = hand_state.tempo_gesture

        if gesture is None:
            self._tempo_gesture_armed = True
            return
        if not self._tempo_gesture_armed:
            return

        self._tempo_gesture_armed = False
        if gesture == "thumbs_up":
            self._set_tempo(next_tempo_step(self.tempo))
        elif gesture == "thumbs_down":
            self._set_tempo(previous_tempo_step(self.tempo))

    def apply_wand_gesture(self, gesture: str) -> None:
        section = self._hand_targeted_section() or "all"

        all_selected = section == "all"
        targets = list(SECTION_ORDER) if all_selected else [section]

        if gesture == "volume_up":
            for s in targets:
                self._set_base_volume(s, self.base_volumes[s] + _VOLUME_STEP)
        elif gesture == "volume_down":
            for s in targets:
                self._set_base_volume(s, self.base_volumes[s] - _VOLUME_STEP)
        elif gesture == "mute":
            for s in targets:
                self.muted[s] = not self.muted[s]
            self._apply_effective_volumes()
        elif gesture == "solo" and not all_selected:
            self.soloed[section] = not self.soloed[section]
            self._apply_effective_volumes()

    def _hand_targeted_section(self, hand_state=None) -> str | None:
        state = self._hand_state() if hand_state is None else hand_state
        if state is None or not state.detected:
            return None
        return state.targeted_section
