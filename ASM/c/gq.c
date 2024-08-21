#include "gq.h"

#define REG_PAGES 6
#define REGS_PER_PAGE 16
#define REGS_PER_GROUP (REG_PAGES * REGS_PER_PAGE)
#define REG_EDITOR_DATA ((int16_t *)0x801C6EA4)
#define BASE_REG(n, r) REG_EDITOR_DATA[(n)*REGS_PER_GROUP + (r)]
#define REG(r) BASE_REG(0, (r))

#define HOOKSHOT_RETICLE_TEXTURE (void *)0x0602BB18
#define LONGSHOT_ICON_TEXTURE (void *)0x0800B000

#define PLAYER_IA_LONGSHOT 0x11

extern uint8_t CFG_DUNGEON_IS_MQ[14];
extern uint8_t GQ_HOOKSHOT_RETICLE_RESOURCE;
extern uint8_t GQ_ULTRASHOT_NAME_RESOURCE;
extern uint8_t GQ_ULTRASHOT_ICON_RESOURCE;

_Bool is_gq_scene(z64_game_t *game);
void draw_item_icon(Gfx **gfx_ptr, void *texture, uint16_t width, uint16_t height);

_Bool is_gq_scene(z64_game_t *game)
{
    return game->scene_index < 14 && CFG_DUNGEON_IS_MQ[game->scene_index] == 2;
}

void set_boot_data(z64_game_t *game, z64_link_t *link)
{
    // Call the original set boot physics function
    z64_LinkSetBootData(game, link);

    // Change boot physics in Gold Quest dungeons
    if (is_gq_scene(game))
    {
        switch (link->current_boots)
        {
        case 0x00:                                        // Kokiri
            REG(45) = z64_file.link_age == 0 ? 650 : 600; // Adult or Child Speed
            break;
        case 0x02:         // Hover
            REG(38) = 300; // Animation
            REG(45) = 800; // Speed
            REG(68) = -69; // Gravity
            break;
        }
    }
}

int32_t set_back_walk_speed(float *value, float target, float incr_step, float decr_step)
{
    if (is_gq_scene(&z64_game))
    {
        target = target * 11.0f / 12.0f;
        incr_step = 1.375f;
    }

    return z64_Math_AsymStepToF(value, target, incr_step, decr_step);
}

void draw_hookshot_reticle(z64_game_t *game, z64_link_t *link, float z_component)
{
    // Get original texture
    void *texture = HOOKSHOT_RETICLE_TEXTURE;

    // Draw hookshot reticle for Gold Quest scenes
    if (is_gq_scene(game))
    {
        // Change range at which ultrashot reticle is drawn
        if (link->held_item_action == PLAYER_IA_LONGSHOT)
        {
            z_component = 310400.0f;
        }

        // Use Gold Quest hookshot reticle texture
        texture = &GQ_HOOKSHOT_RETICLE_RESOURCE;
    }

    // Push custom dlist (that sets the texture) to segment 09
    z64_gfx_t *gfx = game->common.gfx;
    gfx->overlay.d -= 2;
    gDPSetTextureImage(gfx->overlay.d, G_IM_FMT_I, G_IM_SIZ_8b, 1, texture);
    gSPEndDisplayList(gfx->overlay.d + 1);
    gSPSegment(gfx->overlay.p++, 0x09, gfx->overlay.d);

    // Call original draw function
    z64_LinkDrawHookshotReticle(game, link, z_component);
}

int32_t get_hookshot_length()
{
    if (z64_link.held_item_action == 0x11)
    {
        if (is_gq_scene(&z64_game))
        {
            // Ultrashot length
            return 0x68;
        }

        // Longshot length
        return 0x1A;
    }

    // Hookshot length
    return 0x0D;
}

void draw_item_icon(Gfx **gfx_ptr, void *texture, uint16_t width, uint16_t height)
{
    // Use ultrashot icon for Gold Quest scenes
    if (is_gq_scene(&z64_game))
    {
        if (texture == LONGSHOT_ICON_TEXTURE)
        {
            texture = &GQ_ULTRASHOT_ICON_RESOURCE;
        }
    }

    gDPLoadTextureBlock((*gfx_ptr)++, texture, G_IM_FMT_RGBA, G_IM_SIZ_32b, width, height, 0,
                        G_TX_NOMIRROR | G_TX_WRAP, G_TX_NOMIRROR | G_TX_WRAP, G_TX_NOMASK, G_TX_NOMASK, G_TX_NOLOD,
                        G_TX_NOLOD);
}

void draw_item_icon_overlay(z64_gfx_t *gfx, void *texture, uint16_t width, uint16_t height)
{
    draw_item_icon(&gfx->overlay.p, texture, width, height);
}

void draw_item_icon_poly_opa(z64_gfx_t *gfx, void *texture, uint16_t width, uint16_t height)
{
    draw_item_icon(&gfx->poly_opa.p, texture, width, height);
}

void draw_button_item_icon(z64_game_t *game, void *texture, uint16_t button)
{
    // Use ultrashot icon for Gold Quest scenes
    if (is_gq_scene(game))
    {
        if (z64_file.button_items[button] == Z64_ITEM_LONGSHOT)
        {
            texture = &GQ_ULTRASHOT_ICON_RESOURCE;
        }
    }

    z64_InterfaceDrawItemIconTexture(game, texture, button);
}

// Replaces KaleidoScope_QuadTextureIA4
Gfx *draw_menu_item_name(Gfx *gfx_ptr, void *texture, int16_t width, int16_t height, uint16_t point)
{
    // Use ultrashot name for Gold Quest scenes
    if (is_gq_scene(&z64_game))
    {
        if (z64_game.pause_ctxt.item_id == Z64_ITEM_LONGSHOT)
        {
            texture = &GQ_ULTRASHOT_NAME_RESOURCE;
        }
    }

    gDPLoadTextureBlock_4b(gfx_ptr++, texture, G_IM_FMT_IA, width, height, 0, G_TX_NOMIRROR | G_TX_WRAP,
                           G_TX_NOMIRROR | G_TX_WRAP, G_TX_NOMASK, G_TX_NOMASK, G_TX_NOLOD, G_TX_NOLOD);
    gSP1Quadrangle(gfx_ptr++, point, point + 2, point + 3, point + 1, 0);

    return gfx_ptr;
}

// Replaces KaleidoScope_DrawQuadTextureRGBA32
void draw_menu_item_icon(z64_gfx_t *gfx, void *texture, uint16_t width, uint16_t height, uint16_t point)
{
    draw_item_icon_poly_opa(gfx, texture, width, height);
    gSP1Quadrangle(gfx->poly_opa.p++, point, point + 2, point + 3, point + 1, 0);
}

void set_ultrashot_color(z64_gfx_t *gfx)
{
    gfx->poly_opa.d -= 3;
    if (is_gq_scene(&z64_game))
    {
        gDPSetPrimColor(gfx->poly_opa.d, 0, 0, 0xFF, 0xC1, 0x00, 0xFF);
        gDPSetEnvColor(gfx->poly_opa.d + 1, 0x73, 0x57, 0x00, 0xFF);
    }
    else
    {
        gDPSetPrimColor(gfx->poly_opa.d, 0, 0, 0x46, 0x32, 0x46, 0xFF);
        gDPSetEnvColor(gfx->poly_opa.d + 1, 0x14, 0x0A, 0x14, 0xFF);
    }
    gSPEndDisplayList(gfx->poly_opa.d + 2);
    gSPSegment(gfx->poly_opa.p++, 0x09, gfx->poly_opa.d);
}
