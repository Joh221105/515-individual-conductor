"""Pygame song selection screen for built-in demos."""

from __future__ import annotations

import pygame

from .song_catalog import BUILTIN_SONGS, SongConfig


WINDOW_SIZE = (1200, 700)
FPS = 60
BG = (28, 28, 32)
PANEL = (42, 42, 48)
PANEL_ACTIVE = (58, 58, 68)
TEXT = (238, 238, 242)
MUTED_TEXT = (150, 150, 160)
ACCENT = (70, 210, 255)
BORDER = (86, 86, 96)


class SongSelectionUI:
    def __init__(self, songs: tuple[SongConfig, ...] = BUILTIN_SONGS) -> None:
        pygame.init()
        self.songs = songs
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Choose Song")
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont("Arial", 40, bold=True)
        self.font = pygame.font.SysFont("Arial", 26, bold=True)
        self.small_font = pygame.font.SysFont("Arial", 18)
        self.selected_index = 0
        self.running = True
        self.cards = self._build_cards()

    def run(self) -> SongConfig | None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    choice = self._handle_key(event.key)
                    if choice is not None:
                        return choice
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    choice = self._handle_click(event.pos)
                    if choice is not None:
                        return choice

            self._draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()
        return None

    def _build_cards(self) -> list[pygame.Rect]:
        card_width = 320
        card_height = 180
        gap = 28
        total_width = card_width * len(self.songs) + gap * (len(self.songs) - 1)
        x = (WINDOW_SIZE[0] - total_width) // 2
        y = 250
        return [
            pygame.Rect(x + index * (card_width + gap), y, card_width, card_height)
            for index in range(len(self.songs))
        ]

    def _handle_key(self, key: int) -> SongConfig | None:
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.running = False
            return None
        if key in (pygame.K_LEFT, pygame.K_a):
            self.selected_index = max(0, self.selected_index - 1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.selected_index = min(len(self.songs) - 1, self.selected_index + 1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            return self._select_song(self.selected_index)
        elif pygame.K_1 <= key <= pygame.K_9:
            index = key - pygame.K_1
            if index < len(self.songs):
                return self._select_song(index)
        return None

    def _handle_click(self, pos: tuple[int, int]) -> SongConfig | None:
        for index, rect in enumerate(self.cards):
            if rect.collidepoint(pos):
                return self._select_song(index)
        return None

    def _select_song(self, index: int) -> SongConfig:
        self.selected_index = index
        pygame.display.quit()
        return self.songs[index]

    def _draw(self) -> None:
        self.screen.fill(BG)
        title = self.title_font.render("Choose a song to conduct", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WINDOW_SIZE[0] // 2, 120)))
        subtitle = self.small_font.render("Use 1-3, arrow keys + Enter, or click a song.", True, MUTED_TEXT)
        self.screen.blit(subtitle, subtitle.get_rect(center=(WINDOW_SIZE[0] // 2, 162)))

        for index, song in enumerate(self.songs):
            self._draw_card(index, song, self.cards[index])

    def _draw_card(self, index: int, song: SongConfig, rect: pygame.Rect) -> None:
        selected = index == self.selected_index
        fill = PANEL_ACTIVE if selected else PANEL
        border = ACCENT if selected else BORDER
        border_width = 4 if selected else 1
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, border, rect, border_width, border_radius=8)

        number = self.small_font.render(str(index + 1), True, BG if selected else TEXT)
        badge = pygame.Rect(rect.x + 18, rect.y + 18, 32, 32)
        pygame.draw.rect(self.screen, ACCENT if selected else (64, 64, 72), badge, border_radius=16)
        self.screen.blit(number, number.get_rect(center=badge.center))

        title = self.font.render(song.title, True, TEXT)
        self.screen.blit(title, title.get_rect(center=(rect.centerx, rect.centery - 10)))
        hint = self.small_font.render("Select", True, ACCENT if selected else MUTED_TEXT)
        self.screen.blit(hint, hint.get_rect(center=(rect.centerx, rect.centery + 36)))
