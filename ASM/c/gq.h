#ifndef GQ_H
#define GQ_H

#include "z64.h"

void set_boot_data(z64_game_t *game, z64_link_t *link);
int32_t set_back_walk_speed(float *pValue, float target, float incrStep, float decrStep);
void draw_hookshot_reticle(z64_game_t *game, z64_link_t *link, float z_component);
int32_t get_hookshot_length();
void draw_item_icon_overlay(z64_gfx_t *gfx, void *texture, uint16_t width, uint16_t height);
void draw_item_icon_poly_opa(z64_gfx_t *gfx, void *texture, uint16_t width, uint16_t height);
void draw_button_item_icon(z64_game_t *game, void *texture, uint16_t button);
Gfx *draw_menu_item_name(Gfx *gfx_ptr, void *texture, int16_t width, int16_t height, uint16_t point);
void draw_menu_item_icon(z64_gfx_t *gfx, void *texture, uint16_t width, uint16_t height, uint16_t point);
void set_ultrashot_color(z64_gfx_t *gfx);

// TODO.GQ: Gold skulltula flags

// TODO.GQ: Ultrashot get item text
// "\x08\x13\x0BYou found the \x05\x41Ultrashot\x05\x40!\x01It's an upgraded Longshot.\x01\x05\x41Four times longer\x05\x40!!"

// TODO.GQ: Boomerang, ocarina colors

// TODO.GQ: Shield icons and models

// TODO.GQ: Link's hair

// TODO.GQ: Pacman logo

#endif
