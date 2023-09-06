#ifndef MODELS_H
#define MODELS_H

#include <stdint.h>

typedef struct {
    uint16_t object_id;
    uint8_t *buf;
} loaded_object_t;

loaded_object_t *get_object(uint32_t object_id);
void models_init();
void models_reset();

#endif
