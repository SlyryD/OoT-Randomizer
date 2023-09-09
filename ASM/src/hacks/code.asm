.headersize (0x800110A0 - 0xA87000)

; Hook at the start collider_setcylinder so we can override cylinder radii
.org 0x8004acec
; Replaces:
;   addiu   sp, sp, -0x18
;   sw      ra, 0x14(sp)
    j   Collider_SetCylinder_Hook
    nop
Collider_SetCylinder_AfterHook:
